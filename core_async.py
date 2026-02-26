"""
core_async.py — Async Scan Orchestrator
─────────────────────────────────────────
Async version of core.py.

Key upgrade from the old synchronous version:
  • Uses `httpx.AsyncClient` instead of `requests`
  • The `await` keyword means Python can handle OTHER requests
    while waiting for a slow website to respond
  • This is what makes FastAPI truly non-blocking

The scanning analysis (BeautifulSoup, etc.) is CPU-bound, so we
run it in a thread pool via asyncio.to_thread() to keep the
event loop free.
"""

from __future__ import annotations
import time
import asyncio
from dataclasses import asdict

# httpx is the async-friendly HTTP client (pip install httpx)
# It has the same API as requests but supports async/await
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    # Fall back to running requests in a thread if httpx isn't installed
    import requests
    HTTPX_AVAILABLE = False

from scanner.seo_checker         import check_seo
from scanner.bug_checker         import check_bugs
from scanner.performance_checker import check_performance
from ai.suggestion_engine        import enrich_issues_with_suggestions, generate_executive_summary


FETCH_TIMEOUT = 15   # seconds
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (compatible; WebPulseBot/2.0; +https://webpulse.ai/bot)",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
}


# ─────────────────────────────────────────────────────────────────────────────
# Main async entry point
# ─────────────────────────────────────────────────────────────────────────────

async def run_scan_async(url: str) -> dict:
    """
    Async version of run_scan().

    FastAPI calls this with `await run_scan_async(url)`.
    While waiting for the HTTP response, FastAPI can serve
    other requests — no threads blocked.

    Returns the same dict structure as the sync version.
    """
    result: dict = {
        "url":               url,
        "scanned_at":        time.time(),
        "response_time_ms":  0,
        "status_code":       None,
        "scores":            {},
        "issue_counts":      {},
        "issues":            [],
        "meta":              {},
        "stats":             {},
        "executive_summary": "",
        "error":             None,
    }

    # ── Step 1: Fetch the page (async, non-blocking) ──────────────────────────
    html, fetch_ok = await _fetch_url(url, result)
    if not fetch_ok:
        return _finalise(result)

    # ── Step 2: Run all analysers (CPU work → thread pool) ────────────────────
    # asyncio.to_thread() runs a blocking function in a background thread
    # so the event loop stays free for other requests
    try:
        seo_result, bug_result, perf_result = await asyncio.gather(
            asyncio.to_thread(check_seo,         html, url),
            asyncio.to_thread(check_bugs,        html, url),
            asyncio.to_thread(check_performance, html, url, result["response_time_ms"]),
        )
    except Exception as e:
        result["error"] = f"Analysis failed: {str(e)}"
        return _finalise(result)

    # ── Step 3: Merge issues + enrich with AI suggestions ─────────────────────
    all_issues = seo_result["issues"] + bug_result["issues"] + perf_result["issues"]
    all_issues = await asyncio.to_thread(enrich_issues_with_suggestions, all_issues)
    issues_dicts = [asdict(i) for i in all_issues]

    # ── Step 4: Calculate scores ──────────────────────────────────────────────
    scores = {
        "seo":         seo_result["score"],
        "bugs":        bug_result["score"],
        "performance": perf_result["score"],
    }
    scores["overall"] = round((scores["seo"] + scores["bugs"] + scores["performance"]) / 3)

    # ── Step 5: Count issues by severity ──────────────────────────────────────
    issue_counts: dict = {"High": 0, "Medium": 0, "Low": 0}
    for issue in issues_dicts:
        sev = issue.get("severity", "Low")
        issue_counts[sev] = issue_counts.get(sev, 0) + 1

    # ── Step 6: Assemble final result ─────────────────────────────────────────
    result.update({
        "scores":            scores,
        "issue_counts":      issue_counts,
        "issues":            issues_dicts,
        "meta":              seo_result.get("meta", {}),
        "stats":             {**bug_result.get("stats", {}), **perf_result.get("stats", {})},
        "executive_summary": generate_executive_summary(scores, len(issues_dicts)),
    })

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Async HTTP fetcher
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_url(url: str, result: dict) -> tuple[str, bool]:
    """
    Fetch the URL asynchronously.
    Returns (html_string, success_bool).
    Mutates `result` to record status_code, response_time_ms, and error.
    """
    t0 = time.time()

    if HTTPX_AVAILABLE:
        # ── httpx async path (preferred) ──────────────────────────────────────
        try:
            async with httpx.AsyncClient(
                headers=HEADERS,
                timeout=FETCH_TIMEOUT,
                follow_redirects=True,
                verify=False,        # skip SSL verification for auditing purposes
            ) as client:
                response = await client.get(url)
                result["response_time_ms"] = round((time.time() - t0) * 1000, 1)
                result["status_code"]      = response.status_code
                if response.status_code >= 400:
                    result["error"] = f"Server returned HTTP {response.status_code}"
                return response.text, True

        except httpx.TimeoutException:
            result["error"] = f"Request timed out after {FETCH_TIMEOUT}s"
            return "", False
        except httpx.ConnectError as e:
            result["error"] = f"Could not connect to {url}: {str(e)[:100]}"
            return "", False
        except Exception as e:
            result["error"] = f"Fetch failed: {str(e)[:120]}"
            return "", False

    else:
        # ── Fallback: run requests in a thread ────────────────────────────────
        try:
            import requests as req

            def _blocking_fetch():
                return req.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT, allow_redirects=True)

            response = await asyncio.to_thread(_blocking_fetch)
            result["response_time_ms"] = round((time.time() - t0) * 1000, 1)
            result["status_code"]      = response.status_code
            if response.status_code >= 400:
                result["error"] = f"Server returned HTTP {response.status_code}"
            return response.text, True

        except Exception as e:
            result["error"] = f"Fetch failed: {str(e)[:120]}"
            return "", False


def _finalise(result: dict) -> dict:
    """Return a minimal valid result when fetching totally failed."""
    result.setdefault("scores",       {"overall": 0, "seo": 0, "bugs": 0, "performance": 0})
    result.setdefault("issue_counts", {"High": 0, "Medium": 0, "Low": 0})
    result.setdefault("issues",       [])
    return result
