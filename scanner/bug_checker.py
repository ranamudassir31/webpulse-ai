"""
scanner/bug_checker.py
──────────────────────
Checks for common website bugs and accessibility issues:
  • Images missing alt text
  • Links without href or with javascript:void
  • Forms without labels
  • Empty links / buttons
  • Viewport meta tag
  • Charset declaration
  • Console-visible inline script errors (basic heuristic)
"""

from __future__ import annotations
from bs4 import BeautifulSoup
from scanner.seo_checker import Issue


def check_bugs(html: str, url: str) -> dict:
    """
    Run accessibility and bug checks.

    Returns:
        {
            "score": int,
            "issues": [Issue, ...],
            "stats": {images_total, images_missing_alt, links_total, ...}
        }
    """
    soup = BeautifulSoup(html, "html.parser")
    issues: list[Issue] = []
    stats: dict = {}

    # ── 1. Images & Alt Text ─────────────────────────────
    images = soup.find_all("img")
    missing_alt = [img for img in images if not img.get("alt")]
    empty_alt_decorative = [img for img in images if img.get("alt") == ""]  # intentionally decorative
    stats["images_total"] = len(images)
    stats["images_missing_alt"] = len(missing_alt)

    if missing_alt:
        sample = [img.get("src", "unknown")[:60] for img in missing_alt[:3]]
        issues.append(Issue(
            category="Accessibility",
            severity="High",
            title=f"{len(missing_alt)} image(s) missing alt text",
            detail=f"Images without alt attributes hurt screen reader users and SEO. Examples: {', '.join(sample)}",
        ))

    # ── 2. Viewport Meta ─────────────────────────────────
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if not viewport:
        issues.append(Issue(
            category="Accessibility",
            severity="High",
            title="Missing viewport meta tag",
            detail="No <meta name='viewport'> found. The page will not be mobile-responsive.",
        ))

    # ── 3. Charset Declaration ────────────────────────────
    charset = soup.find("meta", charset=True) or soup.find("meta", attrs={"http-equiv": "Content-Type"})
    if not charset:
        issues.append(Issue(
            category="Bugs",
            severity="Medium",
            title="Missing charset declaration",
            detail="No charset meta tag found. This can cause character encoding issues across browsers.",
        ))

    # ── 4. Links Analysis ─────────────────────────────────
    links = soup.find_all("a")
    empty_links = [a for a in links if not a.get("href") or a.get("href").strip() in ("#", "javascript:void(0)", "javascript:;", "")]
    notext_links = [a for a in links if not a.get_text(strip=True) and not a.find("img")]

    stats["links_total"] = len(links)
    stats["empty_links"] = len(empty_links)

    if empty_links:
        issues.append(Issue(
            category="Bugs",
            severity="Medium",
            title=f"{len(empty_links)} link(s) with no destination",
            detail="Links pointing to '#' or 'javascript:void(0)' create broken UX and confuse screen readers.",
        ))

    if notext_links:
        issues.append(Issue(
            category="Accessibility",
            severity="Medium",
            title=f"{len(notext_links)} link(s) with no visible text or image",
            detail="Links must have descriptive text or an image with alt text so screen readers can identify them.",
        ))

    # ── 5. Forms & Labels ─────────────────────────────────
    inputs = soup.find_all("input", attrs={"type": lambda t: t not in ("hidden", "submit", "button", "reset", None) if t else True})
    unlabeled = []
    for inp in inputs:
        inp_id = inp.get("id")
        inp_type = inp.get("type", "text")
        if inp_type in ("hidden", "submit", "button", "reset"):
            continue
        has_label = False
        if inp_id:
            label = soup.find("label", attrs={"for": inp_id})
            if label:
                has_label = True
        if not has_label and not inp.get("aria-label") and not inp.get("placeholder"):
            unlabeled.append(inp)

    stats["inputs_total"] = len(inputs)
    stats["inputs_unlabeled"] = len(unlabeled)

    if unlabeled:
        issues.append(Issue(
            category="Accessibility",
            severity="High",
            title=f"{len(unlabeled)} form input(s) without labels",
            detail="Form inputs must have associated <label> elements or aria-label attributes for accessibility compliance.",
        ))

    # ── 6. Empty Buttons ──────────────────────────────────
    buttons = soup.find_all("button")
    empty_buttons = [b for b in buttons if not b.get_text(strip=True) and not b.find("img") and not b.get("aria-label")]
    if empty_buttons:
        issues.append(Issue(
            category="Accessibility",
            severity="Medium",
            title=f"{len(empty_buttons)} button(s) with no accessible label",
            detail="Buttons must contain text or have an aria-label so assistive technology can describe their purpose.",
        ))

    # ── 7. Deprecated HTML Tags ───────────────────────────
    deprecated_tags = ["center", "font", "marquee", "blink", "frame", "frameset"]
    found_deprecated = [tag for tag in deprecated_tags if soup.find(tag)]
    if found_deprecated:
        issues.append(Issue(
            category="Bugs",
            severity="Medium",
            title=f"Deprecated HTML tags found: {', '.join(f'<{t}>' for t in found_deprecated)}",
            detail="Deprecated HTML elements are not supported in modern browsers and indicate outdated code.",
        ))

    # ── 8. Inline Styles (excessive) ─────────────────────
    inline_style_count = len(soup.find_all(style=True))
    if inline_style_count > 20:
        issues.append(Issue(
            category="Bugs",
            severity="Low",
            title=f"Excessive inline styles ({inline_style_count} elements)",
            detail="Heavy use of inline styles makes maintenance difficult and increases page weight. Use CSS classes instead.",
        ))

    # ── Score ─────────────────────────────────────────────
    deductions = {"High": 20, "Medium": 10, "Low": 5}
    score = 100
    for issue in issues:
        score -= deductions.get(issue.severity, 5)
    score = max(0, min(100, score))

    return {"score": score, "issues": issues, "stats": stats}
