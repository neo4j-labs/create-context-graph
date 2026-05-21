#!/usr/bin/env python3
"""
End-to-end smoke test for create-context-graph.

Scaffolds a project, starts the backend (+ optionally frontend), seeds data,
then sends every demo scenario prompt to the chat API and validates responses.

Usage:
    # API-only smoke test (no browser needed)
    python scripts/e2e_smoke_test.py --domain healthcare --framework pydanticai

    # Full Playwright browser test
    python scripts/e2e_smoke_test.py --domain healthcare --framework pydanticai --browser

    # Test all domains with one framework
    python scripts/e2e_smoke_test.py --all-domains --framework pydanticai

    # Quick mode: only first prompt per scenario
    python scripts/e2e_smoke_test.py --domain healthcare --framework pydanticai --quick

Requirements:
    - Neo4j running (local, Docker, or Aura)
    - LLM API key set (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
    - For --browser: Node.js + Playwright installed
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
import yaml


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BACKEND_PORT = 8111  # Use non-default port to avoid conflicts
FRONTEND_PORT = 3111
HEALTH_URL = f"http://localhost:{BACKEND_PORT}/health"
CHAT_URL = f"http://localhost:{BACKEND_PORT}/api/chat"
CHAT_TIMEOUT = 120  # seconds per prompt

# Minimum quality thresholds
MIN_RESPONSE_LENGTH = 50
MAX_ERROR_RATE = 0.2  # Allow up to 20% failures (some prompts need specific data)


@dataclass
class TestResult:
    domain: str
    framework: str
    scenario: str
    prompt: str
    passed: bool
    response_length: int = 0
    error: str = ""
    duration: float = 0.0


@dataclass
class TestSummary:
    domain: str
    framework: str
    results: list[TestResult] = field(default_factory=list)
    scaffold_ok: bool = False
    backend_started: bool = False
    seed_ok: bool = False

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str, level: str = "INFO") -> None:
    colors = {"INFO": "\033[36m", "OK": "\033[32m", "FAIL": "\033[31m", "WARN": "\033[33m"}
    reset = "\033[0m"
    color = colors.get(level, "")
    print(f"{color}[{level}]{reset} {msg}", flush=True)


def load_demo_scenarios(domain: str) -> list[dict]:
    """Load demo scenarios from domain YAML."""
    domains_dir = Path(__file__).parent.parent / "src" / "create_context_graph" / "domains"
    yaml_path = domains_dir / f"{domain}.yaml"
    if not yaml_path.exists():
        log(f"Domain YAML not found: {yaml_path}", "FAIL")
        return []
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    return data.get("demo_scenarios", [])


def wait_for_backend(timeout: int = 60) -> bool:
    """Wait for backend health endpoint to respond."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            res = requests.get(HEALTH_URL, timeout=5)
            if res.ok:
                status = res.json().get("status", "unknown")
                log(f"Backend ready (status={status})", "OK")
                return True
        except requests.ConnectionError:
            pass
        time.sleep(2)
    log("Backend failed to start within timeout", "FAIL")
    return False


def send_prompt(prompt: str, session_id: str | None = None) -> dict:
    """Send a prompt to the chat API and return the response."""
    payload: dict = {"message": prompt}
    if session_id:
        payload["session_id"] = session_id
    res = requests.post(CHAT_URL, json=payload, timeout=CHAT_TIMEOUT)
    res.raise_for_status()
    return res.json()


def evaluate_response(prompt: str, response: dict) -> tuple[bool, str]:
    """Evaluate whether a chat response is 'good enough'."""
    text = response.get("response", "")

    if not text:
        return False, "Empty response"

    if len(text) < MIN_RESPONSE_LENGTH:
        return False, f"Response too short ({len(text)} chars)"

    # Check for common error patterns
    error_patterns = [
        "cannot reach the backend",
        "internal server error",
        "traceback",
        "connection refused",
    ]
    text_lower = text.lower()
    for pattern in error_patterns:
        if pattern in text_lower:
            return False, f"Error pattern found: '{pattern}'"

    return True, ""


# ---------------------------------------------------------------------------
# Test execution
# ---------------------------------------------------------------------------


def scaffold_project(
    domain: str, framework: str, output_dir: Path, *, backend: str = "bolt"
) -> bool:
    """Scaffold a project using create-context-graph CLI.

    Args:
        domain: domain ID.
        framework: agent framework key.
        output_dir: parent directory; project is written to ``output_dir/test-app``.
        backend: ``"bolt"`` (self-hosted) or ``"nams"`` (hosted). Defaults to bolt
            so the legacy E2E flow (with fixture seeding) keeps working.
    """
    log(f"Scaffolding {domain} + {framework} [{backend}] → {output_dir}")
    cmd = [
        sys.executable, "-m", "create_context_graph",
        "test-app",
        "--domain", domain,
        "--framework", framework,
        "--output-dir", str(output_dir / "test-app"),
    ]

    if backend == "bolt":
        cmd.extend([
            "--self-hosted",
            "--demo-data",
            "--neo4j-uri", os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            "--neo4j-username", os.environ.get("NEO4J_USERNAME", "neo4j"),
            "--neo4j-password", os.environ.get("NEO4J_PASSWORD", "password"),
        ])
    elif backend == "nams":
        nams_key = os.environ.get("MEMORY_API_KEY", "")
        if not nams_key:
            log("MEMORY_API_KEY env var required for --backend nams", "FAIL")
            return False
        cmd.extend([
            "--nams-api-key", nams_key,
            "--demo-data",  # B-partial port: entities land via REST
        ])
        endpoint = os.environ.get("MEMORY_NAMS_ENDPOINT")
        if endpoint:
            cmd.extend(["--nams-endpoint", endpoint])
    else:
        log(f"Unknown backend: {backend}", "FAIL")
        return False

    # Pass agent API keys if available (Anthropic for most, OpenAI for openai-agents)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        cmd.extend(["--anthropic-api-key", api_key])
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        cmd.extend(["--openai-api-key", openai_key])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        log(f"Scaffold failed: {result.stderr[:500]}", "FAIL")
        return False
    log("Scaffold complete", "OK")
    return True


def install_and_seed(project_dir: Path) -> bool:
    """Install backend deps and seed data."""
    backend_dir = project_dir / "backend"

    log("Installing backend dependencies...")
    result = subprocess.run(
        ["uv", "sync"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        log(f"Install failed: {result.stderr[:500]}", "FAIL")
        return False

    log("Seeding demo data...")
    result = subprocess.run(
        ["uv", "run", "python", "scripts/generate_data.py"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        log(f"Seed failed: {result.stderr[:500]}", "WARN")
        # Don't fail — some features work without seed data
    else:
        log("Seed complete", "OK")
    return True


def start_backend(project_dir: Path, framework: str = "") -> subprocess.Popen | None:
    """Start the FastAPI backend server."""
    backend_dir = project_dir / "backend"
    log(f"Starting backend on port {BACKEND_PORT}...")

    cmd = ["uv", "run", "uvicorn", "app.main:app", "--port", str(BACKEND_PORT)]
    # Frameworks using nest_asyncio are incompatible with uvloop
    if framework in ("crewai", "strands", "google-adk"):
        cmd.extend(["--loop", "asyncio"])

    proc = subprocess.Popen(
        cmd,
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )

    if not wait_for_backend():
        proc.terminate()
        return None

    return proc


def run_prompt_tests(
    domain: str,
    framework: str,
    scenarios: list[dict],
    quick: bool = False,
) -> list[TestResult]:
    """Send all demo prompts to the chat API and evaluate responses."""
    results = []
    session_id = None

    for scenario in scenarios:
        name = scenario.get("name", "Unknown")
        prompts = scenario.get("prompts", [])
        if quick:
            prompts = prompts[:1]

        for prompt in prompts:
            log(f"  Testing: {prompt[:80]}...")
            start = time.time()
            try:
                response = send_prompt(prompt, session_id)
                duration = time.time() - start

                # Capture session for multi-turn
                if not session_id:
                    session_id = response.get("session_id")

                passed, error = evaluate_response(prompt, response)
                resp_text = response.get("response", "")
                result = TestResult(
                    domain=domain,
                    framework=framework,
                    scenario=name,
                    prompt=prompt,
                    passed=passed,
                    response_length=len(resp_text),
                    error=error,
                    duration=duration,
                )

                if passed:
                    log(f"    ✓ {len(resp_text)} chars, {duration:.1f}s", "OK")
                else:
                    log(f"    ✗ {error}", "FAIL")
                    if resp_text:
                        log(f"      Response preview: {resp_text[:200]}")

            except Exception as e:
                duration = time.time() - start
                result = TestResult(
                    domain=domain,
                    framework=framework,
                    scenario=name,
                    prompt=prompt,
                    passed=False,
                    error=str(e),
                    duration=duration,
                )
                log(f"    ✗ Exception: {e}", "FAIL")

            results.append(result)

    return results


def run_playwright_tests(project_dir: Path) -> bool:
    """Run Playwright E2E tests on the generated project."""
    frontend_dir = project_dir / "frontend"

    log("Installing Playwright...")
    subprocess.run(
        ["npx", "playwright", "install", "--with-deps", "chromium"],
        cwd=frontend_dir,
        capture_output=True,
        timeout=120,
    )

    log("Running Playwright E2E tests...")
    env = os.environ.copy()
    env["API_URL"] = f"http://localhost:{BACKEND_PORT}"
    env["FRONTEND_URL"] = f"http://localhost:{FRONTEND_PORT}"

    result = subprocess.run(
        ["npx", "playwright", "test", "--reporter=list"],
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )

    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        log("Playwright tests failed", "FAIL")
        return False

    log("Playwright tests passed", "OK")
    return True


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def test_domain(
    domain: str,
    framework: str,
    quick: bool = False,
    browser: bool = False,
    backend: str = "bolt",
) -> TestSummary:
    """Full smoke test for one domain + framework + backend combination."""
    summary = TestSummary(domain=domain, framework=framework)
    scenarios = load_demo_scenarios(domain)

    if not scenarios:
        log(f"No demo scenarios found for {domain}", "FAIL")
        return summary

    log(f"\n{'='*60}")
    log(f"Testing: {domain} + {framework} [{backend}]")
    log(f"  Scenarios: {len(scenarios)}, Prompts: {sum(len(s.get('prompts', [])) for s in scenarios)}")
    log(f"{'='*60}")

    tmpdir = Path(tempfile.mkdtemp(prefix=f"ccg-e2e-{domain}-"))
    backend_proc = None

    try:
        # Scaffold
        if not scaffold_project(domain, framework, tmpdir, backend=backend):
            return summary
        summary.scaffold_ok = True

        project_dir = tmpdir / "test-app"

        # Install + seed
        if not install_and_seed(project_dir):
            return summary
        summary.seed_ok = True

        # Start backend
        backend_proc = start_backend(project_dir, framework)
        if not backend_proc:
            return summary
        summary.backend_started = True

        # Run API-level prompt tests
        summary.results = run_prompt_tests(domain, framework, scenarios, quick)

        # Optionally run Playwright
        if browser:
            # Start frontend too
            frontend_proc = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=project_dir / "frontend",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
                env={**os.environ, "NEXT_PUBLIC_API_URL": f"http://localhost:{BACKEND_PORT}/api"},
            )
            time.sleep(10)  # Wait for Next.js to compile
            try:
                run_playwright_tests(project_dir)
            finally:
                os.killpg(os.getpgid(frontend_proc.pid), signal.SIGTERM)

    finally:
        if backend_proc:
            os.killpg(os.getpgid(backend_proc.pid), signal.SIGTERM)
            backend_proc.wait(timeout=10)

        # Cleanup temp dir
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    return summary


def print_summary(summaries: list[TestSummary]) -> bool:
    """Print final test summary and return True if all passed."""
    print(f"\n{'='*60}")
    print("E2E SMOKE TEST SUMMARY")
    print(f"{'='*60}\n")

    all_passed = True
    for s in summaries:
        status = "PASS" if s.pass_rate >= (1 - MAX_ERROR_RATE) else "FAIL"
        if status == "FAIL":
            all_passed = False

        print(f"  {s.domain} + {s.framework}: {status}")
        print(f"    Scaffold: {'OK' if s.scaffold_ok else 'FAIL'}")
        print(f"    Backend:  {'OK' if s.backend_started else 'FAIL'}")
        print(f"    Seed:     {'OK' if s.seed_ok else 'FAIL'}")
        print(f"    Prompts:  {s.passed}/{s.total} passed ({s.pass_rate:.0%})")

        for r in s.results:
            icon = "✓" if r.passed else "✗"
            print(f"      {icon} [{r.scenario}] {r.prompt[:60]}... ({r.response_length} chars, {r.duration:.1f}s)")
            if r.error:
                print(f"        Error: {r.error}")

        print()

    total = sum(s.total for s in summaries)
    passed = sum(s.passed for s in summaries)
    print(f"Total: {passed}/{total} prompts passed across {len(summaries)} domain(s)")

    return all_passed


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E smoke test for create-context-graph")
    parser.add_argument("--domain", help="Domain to test (e.g., healthcare)")
    parser.add_argument("--framework", default="pydanticai", help="Agent framework (default: pydanticai)")
    parser.add_argument("--all-domains", action="store_true", help="Test all 23 domains")
    parser.add_argument("--quick", action="store_true", help="Only test first prompt per scenario")
    parser.add_argument("--browser", action="store_true", help="Also run Playwright browser tests")
    parser.add_argument(
        "--backend",
        choices=["bolt", "nams"],
        default="bolt",
        help="Memory backend (default: bolt, self-hosted Neo4j). "
             "Use 'nams' to test against the hosted Neo4j Agent Memory Service "
             "(requires MEMORY_API_KEY env).",
    )
    args = parser.parse_args()

    if not args.domain and not args.all_domains:
        parser.error("Specify --domain or --all-domains")

    if args.backend == "nams" and not os.environ.get("MEMORY_API_KEY"):
        parser.error("--backend nams requires MEMORY_API_KEY env var")

    # Determine domains to test
    if args.all_domains:
        domains_dir = Path(__file__).parent.parent / "src" / "create_context_graph" / "domains"
        domains = sorted(
            p.stem for p in domains_dir.glob("*.yaml")
            if not p.stem.startswith("_")
        )
    else:
        domains = [args.domain]

    log(f"Testing {len(domains)} domain(s) with {args.framework} [backend={args.backend}]")
    log(f"Mode: {'quick' if args.quick else 'full'}, Browser: {args.browser}\n")

    summaries = []
    for domain in domains:
        summary = test_domain(
            domain, args.framework, args.quick, args.browser, backend=args.backend
        )
        summaries.append(summary)

    ok = print_summary(summaries)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
