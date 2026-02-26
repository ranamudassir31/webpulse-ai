"""
scanner/performance_checker.py
───────────────────────────────
Estimates page performance from static HTML analysis:
  • Response time measurement
  • HTML page size
  • Number of external scripts / stylesheets (render-blocking risk)
  • Number of external images
  • Minification signals
  • Lazy loading adoption
  • HTTPS check
"""

from __future__ import annotations
import re
from bs4 import BeautifulSoup
from scanner.seo_checker import Issue


def check_performance(html: str, url: str, response_time_ms: float) -> dict:
    """
    Analyse performance signals from the raw HTML.

    Args:
        html:              Raw HTML string
        url:               Page URL (for HTTPS check)
        response_time_ms:  How long the initial fetch took (milliseconds)

    Returns:
        {
            "score": int,
            "issues": [Issue, ...],
            "stats": {page_size_kb, response_time_ms, scripts, stylesheets, ...}
        }
    """
    soup = BeautifulSoup(html, "html.parser")
    issues: list[Issue] = []
    stats: dict = {}

    # ── 1. HTTPS ─────────────────────────────────────────
    if url.startswith("http://"):
        issues.append(Issue(
            category="Performance",
            severity="High",
            title="Site not served over HTTPS",
            detail="The page uses HTTP instead of HTTPS. This hurts SEO rankings and trust, and browsers flag it as insecure.",
        ))

    # ── 2. Response Time ──────────────────────────────────
    stats["response_time_ms"] = round(response_time_ms, 1)
    if response_time_ms > 3000:
        issues.append(Issue(
            category="Performance",
            severity="High",
            title=f"Slow server response time ({response_time_ms:.0f}ms)",
            detail="Server responded in over 3 seconds. Target under 600ms. Investigate server resources, caching, and CDN.",
        ))
    elif response_time_ms > 1500:
        issues.append(Issue(
            category="Performance",
            severity="Medium",
            title=f"High server response time ({response_time_ms:.0f}ms)",
            detail="Server responded in over 1.5 seconds. Consider caching, CDN, or server optimisation to improve TTFB.",
        ))

    # ── 3. Page Size ──────────────────────────────────────
    html_bytes = len(html.encode("utf-8"))
    html_kb = round(html_bytes / 1024, 1)
    stats["page_size_kb"] = html_kb

    if html_kb > 500:
        issues.append(Issue(
            category="Performance",
            severity="High",
            title=f"HTML document is very large ({html_kb} KB)",
            detail="The HTML alone exceeds 500KB. Large pages slow initial load. Consider server-side rendering, lazy loading content, or pagination.",
        ))
    elif html_kb > 150:
        issues.append(Issue(
            category="Performance",
            severity="Medium",
            title=f"HTML document is large ({html_kb} KB)",
            detail="HTML exceeds 150KB. Look for embedded inline scripts, SVGs, or data that could be moved to external files.",
        ))

    # ── 4. Render-Blocking Scripts ────────────────────────
    head = soup.find("head") or soup
    head_scripts = head.find_all("script", src=True)
    blocking_scripts = [s for s in head_scripts if not s.get("defer") and not s.get("async")]
    stats["render_blocking_scripts"] = len(blocking_scripts)

    if blocking_scripts:
        issues.append(Issue(
            category="Performance",
            severity="High" if len(blocking_scripts) > 3 else "Medium",
            title=f"{len(blocking_scripts)} render-blocking script(s) in <head>",
            detail=f"Scripts without async/defer in <head> block page rendering. Add 'defer' or move them before </body>.",
        ))

    # ── 5. External Stylesheets ───────────────────────────
    all_stylesheets = soup.find_all("link", rel="stylesheet")
    stats["external_stylesheets"] = len(all_stylesheets)

    if len(all_stylesheets) > 6:
        issues.append(Issue(
            category="Performance",
            severity="Medium",
            title=f"Many external stylesheets ({len(all_stylesheets)})",
            detail="Too many CSS files increase HTTP requests. Consider bundling or using a build tool like Webpack/Vite.",
        ))

    # ── 6. Total External Scripts ─────────────────────────
    all_scripts = soup.find_all("script", src=True)
    stats["external_scripts"] = len(all_scripts)

    if len(all_scripts) > 10:
        issues.append(Issue(
            category="Performance",
            severity="Medium",
            title=f"High number of external scripts ({len(all_scripts)})",
            detail="Many external scripts increase page weight and introduce third-party latency. Audit and remove unused scripts.",
        ))

    # ── 7. Image Lazy Loading ─────────────────────────────
    images = soup.find_all("img")
    lazy_images = [img for img in images if img.get("loading") == "lazy"]
    stats["images_total"] = len(images)
    stats["images_lazy"] = len(lazy_images)

    if len(images) > 3 and len(lazy_images) == 0:
        issues.append(Issue(
            category="Performance",
            severity="Medium",
            title="No images use lazy loading",
            detail=f"Found {len(images)} images but none use loading='lazy'. Lazy loading improves initial page load time significantly.",
        ))

    # ── 8. Inline CSS Minification Signal ─────────────────
    style_tags = soup.find_all("style")
    for style in style_tags:
        content = style.get_text()
        # Heuristic: unminified CSS has lots of newlines and spaces
        if len(content) > 2000 and content.count("\n") > 50:
            issues.append(Issue(
                category="Performance",
                severity="Low",
                title="Inline CSS appears unminified",
                detail="Large inline <style> blocks could be minified to reduce page size. Consider using a CSS minifier.",
            ))
            break

    # ── 9. Missing favicon ────────────────────────────────
    favicon = soup.find("link", rel=lambda r: r and "icon" in r if isinstance(r, str) else any("icon" in v for v in r) if r else False)
    if not favicon:
        issues.append(Issue(
            category="Performance",
            severity="Low",
            title="No favicon found",
            detail="Missing favicon causes an extra 404 request on every page load and reduces brand presence in browser tabs.",
        ))

    # ── Score ─────────────────────────────────────────────
    deductions = {"High": 20, "Medium": 10, "Low": 5}
    score = 100
    for issue in issues:
        score -= deductions.get(issue.severity, 5)
    score = max(0, min(100, score))

    return {"score": score, "issues": issues, "stats": stats}
