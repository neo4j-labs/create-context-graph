#!/usr/bin/env python3
"""Compare version pins baked into the Jinja templates against upstream.

Dependabot/Renovate cannot read ``*.j2`` manifests, yet those hold the versions
every generated project installs. This script extracts the pins from the
templates (and ``FRAMEWORK_DEPENDENCIES``), queries PyPI / npm / Docker Hub for
the newest release, and reports pins whose *upper bound* would exclude the
current release or whose floor is more than one major behind.

Usage: ``python scripts/check_template_versions.py [--json] [--strict]``
Exit code is non-zero only with ``--strict`` (used by the scheduled workflow).
Network access is required; failures to reach a registry are reported, not fatal.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "create_context_graph"
TEMPLATES = SRC / "templates"

# A quoted requirement: name, optional extras, then an operator followed by a
# digit (so environment-marker strings such as "sys_platform == 'linux'" are skipped).
SPEC_RE = re.compile(r'"([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*([<>=!~]=?\s*\d[^"]*)"')
NPM_RE = re.compile(r'"(@?[A-Za-z0-9_./\-]+)":\s*"([\^~]?\d[^"]*)"')
IMAGE_RE = re.compile(r"(?:image:|FROM)\s+([a-z0-9./\-]+):([A-Za-z0-9._\-]+)")


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "create-context-graph-version-check"})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — https registries only
        return json.load(resp)


def pypi_latest(name: str) -> str | None:
    try:
        return _get(f"https://pypi.org/pypi/{name}/json")["info"]["version"]
    except (urllib.error.URLError, KeyError, ValueError):
        return None


def npm_latest(name: str) -> str | None:
    try:
        return _get(f"https://registry.npmjs.org/{name}/latest")["version"]
    except (urllib.error.URLError, KeyError, ValueError):
        return None


def docker_tags(repo: str, prefix: str) -> list[str]:
    url = f"https://hub.docker.com/v2/repositories/library/{repo}/tags?page_size=100&name={prefix}"
    try:
        data = _get(url)
    except (urllib.error.URLError, ValueError):
        return []
    return sorted({t["name"] for t in data.get("results", []) if re.fullmatch(r"\d+(\.\d+)+", t["name"])})


def _major(version: str) -> int:
    try:
        return int(version.split(".")[0])
    except ValueError:
        return -1


def _cap(spec: str) -> str | None:
    m = re.search(r"<\s*(\d[\w.]*)", spec)
    return m.group(1) if m else None


def _floor(spec: str) -> str | None:
    m = re.search(r">=\s*(\d[\w.]*)", spec)
    return m.group(1) if m else None


def _version_tuple(v: str) -> tuple:
    parts = []
    for piece in re.split(r"[.\-+]", v):
        parts.append(int(piece) if piece.isdigit() else piece)
    return tuple(parts)


def collect_python_pins() -> dict[str, set[str]]:
    pins: dict[str, set[str]] = {}
    sources = [TEMPLATES / "backend" / "shared" / "pyproject.toml.j2", SRC / "config.py"]
    for path in sources:
        for name, spec in SPEC_RE.findall(path.read_text()):
            pins.setdefault(name.lower(), set()).add(spec.strip())
    return pins


def collect_npm_pins() -> dict[str, set[str]]:
    pins: dict[str, set[str]] = {}
    for path in [TEMPLATES / "frontend" / "package.json.j2"]:
        for name, spec in NPM_RE.findall(path.read_text()):
            if name in {"name", "version"}:
                continue
            pins.setdefault(name, set()).add(spec)
    return pins


def collect_images() -> set[tuple[str, str]]:
    images: set[tuple[str, str]] = set()
    for path in (TEMPLATES / "base").glob("*.j2"):
        for repo, tag in IMAGE_RE.findall(path.read_text()):
            images.add((repo, tag))
    return images


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--strict", action="store_true", help="exit 1 when a pin excludes the latest release")
    args = parser.parse_args()

    findings: list[dict] = []

    for name, specs in sorted(collect_python_pins().items()):
        latest = pypi_latest(name)
        if latest is None:
            findings.append({"kind": "pypi", "name": name, "status": "unreachable"})
            continue
        for spec in sorted(specs):
            cap, floor = _cap(spec), _floor(spec)
            status = "ok"
            if cap and _version_tuple(latest) >= _version_tuple(cap):
                status = "latest-excluded-by-cap"
            elif floor and _major(latest) - _major(floor) >= 2:
                status = "floor-two-majors-behind"
            findings.append({"kind": "pypi", "name": name, "spec": spec, "latest": latest, "status": status})

    for name, specs in sorted(collect_npm_pins().items()):
        latest = npm_latest(name)
        if latest is None:
            findings.append({"kind": "npm", "name": name, "status": "unreachable"})
            continue
        for spec in sorted(specs):
            pinned_major = _major(spec.lstrip("^~"))
            status = "ok" if pinned_major == _major(latest) else "major-behind"
            findings.append({"kind": "npm", "name": name, "spec": spec, "latest": latest, "status": status})

    for repo, tag in sorted(collect_images()):
        if repo == "neo4j":
            line = ".".join(tag.split(".")[:2])
            tags = docker_tags("neo4j", line)
            newest = tags[-1] if tags else None
            status = "ok" if newest is None or newest == tag else "newer-patch-available"
            findings.append({"kind": "docker", "name": repo, "spec": tag, "latest": newest, "status": status})
        else:
            findings.append({"kind": "docker", "name": repo, "spec": tag, "status": "pinned" if tag != "latest" else "floating-latest"})

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        width = max(len(f["name"]) for f in findings) if findings else 10
        for f in findings:
            print(f"{f['kind']:6s} {f['name']:{width}s} {f.get('spec', ''):28s} latest={f.get('latest', '?')!s:14s} {f['status']}")

    bad = [f for f in findings if f["status"] in {"latest-excluded-by-cap", "floating-latest"}]
    if bad:
        print(f"\n{len(bad)} pin(s) need attention.", file=sys.stderr)
    return 1 if (args.strict and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
