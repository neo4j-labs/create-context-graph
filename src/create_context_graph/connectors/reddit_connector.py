# Copyright 2026 Neo4j Labs
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Reddit connector — imports posts, comments, and authors from public subreddits.

Uses the Reddit public JSON API (no API key or OAuth required).
Rate limit: ~10 requests/min unauthenticated. A 6-second delay between
requests is applied automatically.

Designed as a general-purpose product discovery and community intelligence
connector. Configure target subreddits and search keywords to track any
product, technology, or topic across Reddit communities.

Subreddits and keywords are configured in config.py via
``REDDIT_DEFAULT_SUBREDDITS`` and ``REDDIT_DEFAULT_KEYWORDS``, or can be
overridden at runtime through the credential prompts.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)
from create_context_graph.config import REDDIT_DEFAULT_KEYWORDS, REDDIT_DEFAULT_SUBREDDITS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.reddit.com"
RESULTS_PER_PAGE = 100
REQUEST_DELAY = 6.0   # seconds between search requests (public API limit ~10 req/min)
COMMENT_DELAY = 3.0   # seconds between comment fetches (lighter endpoint)

HEADERS = {
    "User-Agent": "python:neo4j-context-graph:v1.0 (research pipeline; neo4j-labs)",
    "Accept": "application/json",
}

_ENRICHMENT_SYSTEM_PROMPT = """You are a data extraction assistant. Extract structured product discovery insights from Reddit posts.

Return ONLY valid JSON with this exact structure:
{
  "pain_points": ["concise description of a specific problem or frustration mentioned"],
  "use_cases": ["concise description of a specific application or use case mentioned"],
  "topics": ["topic tag"],
  "technologies": ["ProductOrToolName"]
}

Rules:
- pain_points: real problems, frustrations, or unmet needs the author describes, max 3, empty list if none
- use_cases: concrete applications, workflows, or patterns being built or described, max 3, empty list if none
- topics: 1-4 word subject tags describing the discussion theme (e.g. "performance", "getting started", "integration"), max 5
- technologies: proper-cased product, tool, or service names explicitly mentioned, max 10
- Return empty lists if nothing relevant found, never null"""


def _enrich_post(title: str, body: str, api_key: str) -> dict:
    """Call Claude Haiku to extract pain points, use cases, topics, and technologies from a post."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        text = f"Title: {title}\n\n{body[:2000]}"
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_ENRICHMENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as exc:
        logger.debug("Enrichment failed for post '%s': %s", title[:50], exc)
        return {}


def _get_json(url: str, params: dict | None = None, retries: int = 3) -> dict | None:
    """Fetch a Reddit JSON endpoint, respecting rate limits."""
    if params:
        query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{query}"

    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = 30 * attempt
                logger.warning("Reddit rate-limited. Sleeping %ds…", wait)
                time.sleep(wait)
                continue
            if exc.code in (403, 404):
                return None
            logger.warning("HTTP %d on attempt %d/%d: %s", exc.code, attempt, retries, url)
        except Exception as exc:
            logger.warning("Request error (attempt %d/%d): %s", attempt, retries, exc)
            time.sleep(5 * attempt)
    return None


def _parse_timestamp(ts: Any) -> str:
    """Convert a Unix timestamp (int/float) to an ISO-8601 string."""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return datetime.now(tz=timezone.utc).isoformat()


@register_connector("reddit")
class RedditConnector(BaseConnector):
    """Import posts and comments from Reddit via the public JSON API.

    No API key or OAuth is required. Configure target subreddits and keywords
    in ``config.py`` (``REDDIT_DEFAULT_SUBREDDITS`` / ``REDDIT_DEFAULT_KEYWORDS``),
    or override them through the credential prompts at runtime.
    """

    service_name = "Reddit"
    service_description = (
        "Import posts and comments from Reddit subreddits for product discovery and community intelligence — "
        "no API key required. Configure target subreddits and search keywords in config.py."
    )
    requires_oauth = False

    def __init__(self) -> None:
        self._subreddits: list[str] = list(REDDIT_DEFAULT_SUBREDDITS)
        self._keywords: list[str] = list(REDDIT_DEFAULT_KEYWORDS)
        self._max_pages: int = 1
        self._fetch_comments: bool = True
        self._enrich_posts: bool = True
        self._anthropic_api_key: str | None = None
        self._max_post_age_days: int = 1095  # ~3 years

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "subreddits",
                "prompt": "Subreddits to scrape (comma-separated, or leave blank for defaults):",
                "secret": False,
                "optional": True,
                "description": (
                    f"Defaults: {', '.join(REDDIT_DEFAULT_SUBREDDITS[:4])}, …  "
                    "Override by listing subreddits without the r/ prefix."
                ),
            },
            {
                "name": "keywords",
                "prompt": "Search keywords (comma-separated, or leave blank for defaults):",
                "secret": False,
                "optional": True,
                "description": (
                    f"Defaults: {', '.join(REDDIT_DEFAULT_KEYWORDS[:4])}, …  "
                    "Posts matching any keyword in any target subreddit are imported."
                ),
            },
            {
                "name": "max_pages",
                "prompt": "Max pages per keyword/subreddit combination (default: 1, max 100 posts/page):",
                "secret": False,
                "optional": True,
                "description": "1 page ≈ 100 posts. Increase for deeper historical data.",
            },
            {
                "name": "fetch_comments",
                "prompt": "Fetch post comments? (yes/no, default: yes):",
                "secret": False,
                "optional": True,
                "description": "Fetching comments makes the import slower (~3s extra per post).",
            },
            {
                "name": "enrich_posts",
                "prompt": "Enrich posts with LLM extraction of pain points, use cases, and topics? (yes/no, default: yes):",
                "secret": False,
                "optional": True,
                "description": "Uses ANTHROPIC_API_KEY and claude-haiku to extract PainPoint, UseCase, Topic, and Technology entities from each post.",
            },
        ]

    def authenticate(self, credentials: dict[str, str]) -> None:
        """Store scrape configuration. No authentication token is needed."""
        raw_subs = (credentials.get("subreddits") or "").strip()
        raw_kws = (credentials.get("keywords") or "").strip()
        raw_pages = (credentials.get("max_pages") or "").strip()
        raw_comments = (credentials.get("fetch_comments") or "yes").strip().lower()

        self._subreddits = (
            [s.strip() for s in raw_subs.split(",") if s.strip()]
            or list(REDDIT_DEFAULT_SUBREDDITS)
        )
        self._keywords = (
            [k.strip() for k in raw_kws.split(",") if k.strip()]
            or list(REDDIT_DEFAULT_KEYWORDS)
        )
        self._max_pages = max(1, int(raw_pages)) if raw_pages.isdigit() else 1
        self._fetch_comments = raw_comments not in ("no", "false", "0", "n")
        raw_enrich = (credentials.get("enrich_posts") or "yes").strip().lower()
        self._enrich_posts = raw_enrich not in ("no", "false", "0", "n")
        self._anthropic_api_key: str | None = (
            credentials.get("anthropic_api_key")
            or os.environ.get("ANTHROPIC_API_KEY")
        )

        logger.info(
            "Reddit connector configured: %d subreddits, %d keywords, "
            "max_pages=%d, fetch_comments=%s",
            len(self._subreddits),
            len(self._keywords),
            self._max_pages,
            self._fetch_comments,
        )

    def fetch(self, **kwargs: Any) -> NormalizedData:
        """Scrape configured subreddits and return normalised data.

        Entity labels used (matches the graph-data-community domain):
          Person      — Reddit authors
          Subreddit   — communities
          Post        — Reddit posts
          Comment     — post comments
          Technology  — tech/product entities detected in post text
          Topic       — subject tags extracted from flair / title keywords
          PainPoint   — problems/frustrations extracted via LLM enrichment
          UseCase     — applications/patterns extracted via LLM enrichment
        """
        anthropic_api_key = self._anthropic_api_key if self._enrich_posts else None
        if self._enrich_posts and anthropic_api_key:
            logger.info("LLM enrichment enabled — PainPoints, UseCases, Technologies, and Topics will be extracted.")
        elif self._enrich_posts and not anthropic_api_key:
            logger.warning("enrich_posts=yes but no Anthropic API key found — skipping LLM enrichment.")
        else:
            logger.info("LLM enrichment disabled.")

        entities: dict[str, list[dict]] = {
            "Person": [],
            "Subreddit": [],
            "Post": [],
            "Comment": [],
            "Technology": [],
            "Topic": [],
            "PainPoint": [],
            "UseCase": [],
        }

        seen_pain_points: set[str] = set()
        seen_use_cases: set[str] = set()
        relationships: list[dict] = []
        documents: list[dict] = []

        seen_post_ids: set[str] = set()
        seen_users: set[str] = set()
        seen_subs: set[str] = set()
        seen_techs: set[str] = set()
        seen_topics: set[str] = set()

        # ----------------------------------------------------------------
        # Helpers
        # ----------------------------------------------------------------

        def _ensure_subreddit(name: str) -> None:
            key = name.lower()
            if key not in seen_subs:
                seen_subs.add(key)
                entities["Subreddit"].append({
                    "name": key,
                    "url": f"https://www.reddit.com/r/{key}/",
                    "description": f"r/{key} community",
                })

        def _ensure_user(username: str) -> None:
            if username and username not in seen_users:
                seen_users.add(username)
                entities["Person"].append({
                    "name": username,
                    "role": "reddit-user",
                    "description": f"Reddit user u/{username}",
                })

        def _ensure_technology(name: str) -> None:
            if name and name not in seen_techs:
                seen_techs.add(name)
                entities["Technology"].append({
                    "name": name,
                    "description": f"Technology/product mentioned in community posts",
                })

        def _ensure_topic(name: str) -> None:
            if name and name not in seen_topics:
                seen_topics.add(name)
                entities["Topic"].append({
                    "name": name,
                    "description": f"Discussion topic found in r/ communities",
                })

        # Pre-populate Product/Technology nodes directly from the keyword list.
        # Keywords are treated as product/topic names — proper-cased for display.
        for kw in self._keywords:
            if len(kw) > 2:
                _ensure_technology(kw.title())

        # ----------------------------------------------------------------
        # Scrape
        # ----------------------------------------------------------------
        for sub_idx, subreddit in enumerate(self._subreddits, 1):
            sub_key = subreddit.lower()
            logger.info("[%d/%d] Scraping r/%s", sub_idx, len(self._subreddits), sub_key)
            _ensure_subreddit(sub_key)

            for keyword in self._keywords:
                logger.info("  Keyword '%s' in r/%s…", keyword, sub_key)
                params: dict[str, Any] = {
                    "q": keyword,
                    "sort": "new",
                    "restrict_sr": "on",
                    "limit": RESULTS_PER_PAGE,
                    "t": "all",
                    "raw_json": 1,
                }
                url = f"{BASE_URL}/r/{sub_key}/search.json"
                after: str | None = None
                page = 0

                while page < self._max_pages:
                    if after:
                        params["after"] = after
                    time.sleep(REQUEST_DELAY)
                    data = _get_json(url, params=params)
                    if not data or not isinstance(data, dict):
                        break

                    listing = data.get("data", {})
                    children = listing.get("children", [])
                    if not children:
                        break

                    new_posts: list[dict] = []
                    for child in children:
                        d = child.get("data", {})
                        pid = d.get("id")
                        if not pid or pid in seen_post_ids:
                            continue

                        # Age filter
                        try:
                            age = (
                                datetime.now(tz=timezone.utc)
                                - datetime.fromtimestamp(float(d.get("created_utc", 0)), tz=timezone.utc)
                            ).total_seconds() / 86400
                            if age > self._max_post_age_days:
                                continue
                        except Exception:
                            pass

                        seen_post_ids.add(pid)

                        author = d.get("author", "")
                        if author in ("[deleted]", ""):
                            author = None
                        flair = d.get("link_flair_text") or ""
                        created = _parse_timestamp(d.get("created_utc", 0))
                        title = d.get("title", "")
                        body = d.get("selftext", "")

                        new_posts.append({
                            "pid": pid,
                            "subreddit": sub_key,
                            "title": title,
                            "body": body,
                            "author": author,
                            "score": int(d.get("score", 0)),
                            "upvote_ratio": float(d.get("upvote_ratio", 0.0)),
                            "num_comments": int(d.get("num_comments", 0)),
                            "flair": flair,
                            "permalink": f"https://www.reddit.com{d.get('permalink', '')}",
                            "created": created,
                            "is_self": bool(d.get("is_self", True)),
                        })

                    # Fetch comments before building entities (progress logging)
                    if self._fetch_comments and new_posts:
                        logger.info(
                            "  Fetching comments for %d posts (~%ds)…",
                            len(new_posts),
                            int(len(new_posts) * COMMENT_DELAY),
                        )

                    for i, post in enumerate(new_posts, 1):
                        pid = post["pid"]
                        title = post["title"]
                        body = post["body"]
                        author = post["author"]
                        sub_key = post["subreddit"]

                        # Post entity
                        entities["Post"].append({
                            "name": f"{pid}: {title[:80]}",
                            "post_id": pid,
                            "subreddit": sub_key,
                            "title": title,
                            "body": body[:2000],
                            "score": post["score"],
                            "upvote_ratio": post["upvote_ratio"],
                            "num_comments": post["num_comments"],
                            "flair": post["flair"],
                            "permalink": post["permalink"],
                            "created_utc": post["created"],
                            "is_self": post["is_self"],
                        })

                        # Author
                        if author:
                            _ensure_user(author)
                            relationships.append({
                                "type": "POSTED",
                                "source_name": author,
                                "source_label": "Person",
                                "target_name": f"{pid}: {title[:80]}",
                                "target_label": "Post",
                            })
                            relationships.append({
                                "type": "ACTIVE_IN",
                                "source_name": author,
                                "source_label": "Person",
                                "target_name": sub_key,
                                "target_label": "Subreddit",
                            })

                        # Post → Subreddit
                        relationships.append({
                            "type": "IN_SUBREDDIT",
                            "source_name": f"{pid}: {title[:80]}",
                            "source_label": "Post",
                            "target_name": sub_key,
                            "target_label": "Subreddit",
                        })

                        # Keyword → Technology link
                        tech = keyword.title() if len(keyword) > 2 else None
                        if tech:
                            _ensure_technology(tech)
                            relationships.append({
                                "type": "MENTIONS",
                                "source_name": f"{pid}: {title[:80]}",
                                "source_label": "Post",
                                "target_name": tech,
                                "target_label": "Technology",
                            })

                        # Flair → Topic
                        if post["flair"]:
                            _ensure_topic(post["flair"])
                            relationships.append({
                                "type": "TAGGED_WITH",
                                "source_name": f"{pid}: {title[:80]}",
                                "source_label": "Post",
                                "target_name": post["flair"],
                                "target_label": "Topic",
                            })

                        # LLM enrichment — PainPoints, UseCases, Topics, Technologies
                        if anthropic_api_key:
                            enriched = _enrich_post(title, body, anthropic_api_key)
                            post_name = f"{pid}: {title[:80]}"

                            for pp in enriched.get("pain_points", []):
                                pp = pp.strip()
                                if pp:
                                    if pp not in seen_pain_points:
                                        seen_pain_points.add(pp)
                                        entities["PainPoint"].append({
                                            "name": pp,
                                            "description": pp,
                                            "frequency": 1,
                                    })
                                    relationships.append({
                                        "type": "HAS_PAIN_POINT",
                                        "source_name": post_name,
                                        "source_label": "Post",
                                        "target_name": pp,
                                        "target_label": "PainPoint",
                                    })

                            for uc in enriched.get("use_cases", []):
                                uc = uc.strip()
                                if uc:
                                    if uc not in seen_use_cases:
                                    seen_use_cases.add(uc)
                                    entities["UseCase"].append({
                                        "name": uc,
                                        "description": uc,
                                        "frequency": 1,
                                    })
                                    relationships.append({
                                    "type": "DEMONSTRATES",
                                    "source_name": post_name,
                                    "source_label": "Post",
                                    "target_name": uc,
                                    "target_label": "UseCase",
                                    })

                            for topic in enriched.get("topics", []):
                                topic = topic.strip()
                                if topic:
                                    _ensure_topic(topic)
                                    relationships.append({
                                        "type": "TAGGED_WITH",
                                        "source_name": post_name,
                                        "source_label": "Post",
                                        "target_name": topic,
                                        "target_label": "Topic",
                                    })

                            for tech in enriched.get("technologies", []):
                                tech = tech.strip()
                                if tech:
                                    _ensure_technology(tech)
                                    relationships.append({
                                        "type": "MENTIONS",
                                        "source_name": post_name,
                                        "source_label": "Post",
                                        "target_name": tech,
                                        "target_label": "Technology",
                                    })

                        # Post body as document
                        full_text = f"{title}\n\n{body}".strip()
                        if full_text:
                            documents.append({
                                "title": f"r/{sub_key}: {title[:80]}",
                                "content": full_text[:4000],
                                "type": "reddit-post",
                                "metadata": {
                                    "post_id": pid,
                                    "subreddit": sub_key,
                                    "author": author or "[deleted]",
                                    "score": post["score"],
                                    "permalink": post["permalink"],
                                    "keyword": keyword,
                                },
                            })

                        # Comments
                        if self._fetch_comments:
                            logger.info(
                                "    [%d/%d] comments for %s", i, len(new_posts), pid
                            )
                            comments = self._fetch_post_comments(pid, sub_key)
                            for comment in comments:
                                c_author = comment.get("author")
                                c_body = comment.get("body", "")
                                c_id = comment.get("id", "")
                                c_name = f"{c_id}: {c_body[:60]}"

                                entities["Comment"].append({
                                    "name": c_name,
                                    "comment_id": c_id,
                                    "post_id": pid,
                                    "body": c_body[:1000],
                                    "score": comment.get("score", 0),
                                    "depth": comment.get("depth", 0),
                                    "created_utc": comment.get("created_utc", ""),
                                    "permalink": comment.get("permalink", ""),
                                    "is_top_level": comment.get("depth", 0) == 0,
                                })

                                # Comment → Post
                                relationships.append({
                                    "type": "ON_POST",
                                    "source_name": c_name,
                                    "source_label": "Comment",
                                    "target_name": f"{pid}: {title[:80]}",
                                    "target_label": "Post",
                                })

                                # Author → Comment
                                if c_author:
                                    _ensure_user(c_author)
                                    relationships.append({
                                        "type": "AUTHORED_BY",
                                        "source_name": c_name,
                                        "source_label": "Comment",
                                        "target_name": c_author,
                                        "target_label": "Person",
                                    })
                                    relationships.append({
                                        "type": "ACTIVE_IN",
                                        "source_name": c_author,
                                        "source_label": "Person",
                                        "target_name": sub_key,
                                        "target_label": "Subreddit",
                                    })

                    after = listing.get("after")
                    if not after:
                        break
                    page += 1

            if sub_idx < len(self._subreddits):
                time.sleep(REQUEST_DELAY)

        total_entities = sum(len(v) for v in entities.values())
        logger.info(
            "Reddit import complete: %d entities, %d relationships, %d documents",
            total_entities, len(relationships), len(documents),
        )
        return NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_post_comments(self, post_id: str, subreddit: str, max_comments: int = 50) -> list[dict]:
        """Fetch top-level comments for a single post."""
        url = f"{BASE_URL}/r/{subreddit}/comments/{post_id}.json?raw_json=1"
        time.sleep(COMMENT_DELAY)
        data = _get_json(url)
        if not data or not isinstance(data, list) or len(data) < 2:
            return []

        comments = []
        for child in data[1].get("data", {}).get("children", [])[:max_comments]:
            if child.get("kind") != "t1":
                continue
            d = child.get("data", {})
            body = d.get("body", "")
            if body in ("[deleted]", "[removed]", ""):
                continue
            author = d.get("author", "")
            if author in ("[deleted]", ""):
                author = None
            comments.append({
                "id": d.get("id", ""),
                "body": body,
                "author": author,
                "score": int(d.get("score", 0)),
                "depth": int(d.get("depth", 0)),
                "created_utc": _parse_timestamp(d.get("created_utc", 0)),
                "permalink": f"https://www.reddit.com{d.get('permalink', '')}",
            })
        return comments
