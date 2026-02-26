"""
ai/suggestion_engine.py
────────────────────────
Converts raw technical Issue objects into business-friendly,
actionable recommendations — without needing an external AI API.

The engine uses a rich lookup table keyed on issue titles / categories,
then falls back to a template-based generator for unknown issues.
"""

from __future__ import annotations
from scanner.seo_checker import Issue

# ──────────────────────────────────────────────────────────────────────────────
# Suggestion knowledge base
# Maps fragments of issue titles → human-friendly recommendations
# ──────────────────────────────────────────────────────────────────────────────

SUGGESTION_MAP: dict[str, str] = {
    # SEO
    "missing page title": (
        "Add a unique, descriptive <title> tag to every page (50–60 characters). "
        "Include your main keyword naturally. Example: 'Expert Web Design Services | YourBrand'."
    ),
    "page title too short": (
        "Expand your page title to at least 40 characters. Include your primary keyword "
        "and brand name to maximise click-through rates from search results."
    ),
    "page title too long": (
        "Trim your page title to under 60 characters so search engines display it fully. "
        "Put the most important keyword first."
    ),
    "missing meta description": (
        "Write a compelling meta description of 120–160 characters for each page. "
        "Include a clear value proposition and a call to action — this is what users read before clicking your link in Google."
    ),
    "meta description too short": (
        "Expand your meta description to at least 120 characters. Describe the page value "
        "clearly and include relevant keywords naturally."
    ),
    "meta description too long": (
        "Shorten your meta description to under 160 characters to prevent it being cut off "
        "in search results, which reduces click-through rates."
    ),
    "missing h1 tag": (
        "Add a single H1 heading that clearly describes your page's main topic or service. "
        "This is one of the most important on-page SEO signals. Example: 'Professional Digital Marketing Services'."
    ),
    "multiple h1 tags": (
        "Keep exactly one H1 per page. Merge or demote extra H1s to H2 to maintain a clear content hierarchy "
        "that both users and search engines can follow."
    ),
    "heading hierarchy skips": (
        "Use sequential heading levels (H1 → H2 → H3) without skipping. "
        "This improves document structure, screen reader navigation, and SEO crawlability."
    ),
    "missing canonical tag": (
        "Add <link rel='canonical' href='YOUR-URL'> to prevent duplicate content penalties. "
        "This tells Google which version of the page to index when multiple URLs serve the same content."
    ),
    "incomplete open graph": (
        "Add og:title, og:description, and og:image meta tags. When your page is shared on LinkedIn, "
        "Facebook, or WhatsApp, these control the preview — a compelling image and description dramatically increases shares and clicks."
    ),
    "page set to noindex": (
        "Remove the 'noindex' directive unless you intentionally want this page hidden from search engines. "
        "If this is your main content page, removing noindex could significantly increase organic traffic."
    ),
    "missing lang attribute": (
        "Add a lang attribute to your <html> tag (e.g., <html lang='en'>). "
        "This helps screen readers use the correct pronunciation and assists multilingual SEO."
    ),
    # Accessibility / Bugs
    "image(s) missing alt text": (
        "Add descriptive alt text to every meaningful image. Alt text helps visually impaired users "
        "understand your content and gives search engines additional keyword context. "
        "Example: alt='Team of web developers working in a modern office'."
    ),
    "missing viewport meta tag": (
        "Add <meta name='viewport' content='width=device-width, initial-scale=1'> to your <head>. "
        "Without it, your site will appear zoomed-out and unusable on mobile devices — "
        "which now account for over 60% of web traffic."
    ),
    "missing charset declaration": (
        "Add <meta charset='UTF-8'> as the first element inside <head>. "
        "Without it, special characters (accents, symbols, emojis) may display incorrectly in some browsers."
    ),
    "link(s) with no destination": (
        "Replace placeholder links (#) with real URLs or remove them. "
        "Broken navigation confuses users and tells search engines your site is incomplete."
    ),
    "link(s) with no visible text": (
        "Every link must have descriptive anchor text or an image with alt text. "
        "Screen readers read link text aloud — 'click here' or empty links are useless for accessibility."
    ),
    "form input(s) without labels": (
        "Associate every form input with a <label> element using matching 'for' and 'id' attributes. "
        "Labelled inputs are required for WCAG compliance and make forms easier to use on mobile."
    ),
    "button(s) with no accessible label": (
        "Add descriptive aria-label attributes to icon-only buttons. "
        "Example: <button aria-label='Open navigation menu'>☰</button>. "
        "Screen reader users cannot otherwise identify the button's purpose."
    ),
    "deprecated html tags": (
        "Replace deprecated tags (<center>, <font>, <marquee>) with modern CSS equivalents. "
        "These tags are unsupported in current browsers and signal outdated code to both users and search engines."
    ),
    "excessive inline styles": (
        "Move repeated inline styles to a CSS stylesheet or utility classes. "
        "This reduces HTML file size, improves caching, and makes future design updates much faster."
    ),
    # Performance
    "not served over https": (
        "Install an SSL certificate and redirect all HTTP traffic to HTTPS immediately. "
        "Google penalises non-HTTPS sites in rankings, and browsers show a 'Not Secure' warning that destroys user trust."
    ),
    "slow server response time": (
        "Investigate your server response time (TTFB). Quick wins include: enabling server-side caching, "
        "using a CDN (Cloudflare is free), upgrading your hosting plan, and optimising database queries."
    ),
    "high server response time": (
        "Improve your server response time by enabling caching (Redis/Memcached), "
        "using a CDN for static assets, and reviewing slow database queries."
    ),
    "html document is very large": (
        "Reduce your HTML payload by removing unused content, paginating long pages, "
        "and moving large data (tables, SVGs) to lazy-loaded components."
    ),
    "html document is large": (
        "Reduce HTML size by removing inline scripts and styles, using external files that "
        "browsers can cache between page loads."
    ),
    "render-blocking script(s)": (
        "Add the 'defer' attribute to non-critical <script> tags in <head>. "
        "This allows the browser to parse HTML first, significantly improving perceived load speed "
        "and Core Web Vitals scores."
    ),
    "many external stylesheets": (
        "Bundle your CSS files using a build tool like Vite, Webpack, or Parcel. "
        "Fewer HTTP requests means faster page loads, especially on mobile connections."
    ),
    "high number of external scripts": (
        "Audit your third-party scripts. Every external script adds latency and is a potential point of failure. "
        "Remove unused scripts and consider self-hosting critical ones."
    ),
    "no images use lazy loading": (
        "Add loading='lazy' to all <img> tags below the fold. "
        "This defers loading off-screen images until the user scrolls to them, "
        "significantly improving initial page load time and Largest Contentful Paint (LCP)."
    ),
    "inline css appears unminified": (
        "Minify inline <style> blocks using a CSS minifier (e.g., cssnano). "
        "Minification removes whitespace and comments to reduce file size without affecting functionality."
    ),
    "no favicon found": (
        "Add a favicon.ico and link it in your <head>. A favicon appears in browser tabs, bookmarks, "
        "and mobile home screens — it's a small but visible trust signal for your brand."
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def enrich_issues_with_suggestions(issues: list[Issue]) -> list[Issue]:
    """
    Iterate over issues and attach a human-readable suggestion to each.
    Modifies issues in-place and returns the list.
    """
    for issue in issues:
        issue.suggestion = _find_suggestion(issue)
    return issues


def _find_suggestion(issue: Issue) -> str:
    """Look up a suggestion by matching fragments of the issue title."""
    title_lower = issue.title.lower()

    for key, suggestion in SUGGESTION_MAP.items():
        if key in title_lower:
            return suggestion

    # ── Fallback template ─────────────────────────────────
    severity_advice = {
        "High":   "This issue has a significant impact on your site's performance or visibility and should be addressed as soon as possible.",
        "Medium": "This issue affects user experience or SEO and is worth fixing in your next development sprint.",
        "Low":    "This is a minor improvement that will contribute to overall site quality.",
    }

    return (
        f"{severity_advice.get(issue.severity, 'Review and address this issue.')} "
        f"Category: {issue.category}. "
        f"Technical detail: {issue.detail}"
    )


def generate_executive_summary(scores: dict, total_issues: int) -> str:
    """
    Generate a plain-English executive summary for the report.
    """
    overall = scores.get("overall", 0)
    seo = scores.get("seo", 0)
    accessibility = scores.get("accessibility", 0)  
    performance = scores.get("performance", 0)

    if overall >= 85:
        quality = "excellent"
        outlook = "Minor improvements will push it to near-perfect."
    elif overall >= 65:
        quality = "good"
        outlook = "Addressing the highlighted issues will meaningfully improve rankings and conversions."
    elif overall >= 45:
        quality = "fair"
        outlook = "Several important issues need attention to reach competitive standards."
    else:
        quality = "needs significant improvement"
        outlook = "Resolving the high-severity issues should be prioritised immediately."

    weakest = min(scores, key=lambda k: scores[k] if k != "overall" else 999)
    weakest_labels = {"seo": "SEO", "bugs": "Accessibility & Code Quality", "performance": "Performance"}

    return (
        f"This website audit identified {total_issues} issue(s) across SEO, accessibility, and performance. "
        f"The overall quality score is {overall}/100, which is {quality}. "
        f"The weakest area is {weakest_labels.get(weakest, weakest)} (score: {scores.get(weakest, 0)}/100). "
        f"{outlook}"
    )
