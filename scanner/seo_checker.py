"""
scanner/seo_checker.py
─────────────────────
Analyses the parsed HTML of a webpage for SEO-related signals:
title, meta description, heading hierarchy, canonical, Open Graph, etc.
Returns a list of Issue objects and a numeric score (0–100).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from bs4 import BeautifulSoup


# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────
@dataclass
class Issue:
    category: str          # e.g. "SEO", "Accessibility", "Performance"
    severity: str          # "High" | "Medium" | "Low"
    title: str             # Short label
    detail: str            # Technical explanation
    suggestion: str = ""   # AI-friendly fix (populated later by suggestion engine)


# ──────────────────────────────────────────────
# SEO checker
# ──────────────────────────────────────────────

def check_seo(html: str, url: str) -> dict:
    """
    Run all SEO checks against the raw HTML string.

    Returns:
        {
            "score": int,
            "issues": [Issue, ...],
            "meta": {title, description, h1, canonical, og_title, ...}
        }
    """
    soup = BeautifulSoup(html, "html.parser")
    issues: list[Issue] = []
    meta_info: dict = {}

    # ── 1. Page Title ──────────────────────────────────────
    title_tag = soup.find("title")
    if not title_tag or not title_tag.get_text(strip=True):
        issues.append(Issue(
            category="SEO",
            severity="High",
            title="Missing page title",
            detail="No <title> tag found in the <head> section.",
        ))
        meta_info["title"] = None
    else:
        title_text = title_tag.get_text(strip=True)
        meta_info["title"] = title_text
        if len(title_text) < 10:
            issues.append(Issue(
                category="SEO",
                severity="Medium",
                title="Page title too short",
                detail=f"Title is only {len(title_text)} characters. Aim for 50–60.",
            ))
        elif len(title_text) > 70:
            issues.append(Issue(
                category="SEO",
                severity="Low",
                title="Page title too long",
                detail=f"Title is {len(title_text)} characters. Keep it under 70 to avoid truncation in SERPs.",
            ))

    # ── 2. Meta Description ────────────────────────────────
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not meta_desc.get("content", "").strip():
        issues.append(Issue(
            category="SEO",
            severity="High",
            title="Missing meta description",
            detail="No meta description tag found. Search engines use this as the page snippet.",
        ))
        meta_info["description"] = None
    else:
        desc_text = meta_desc["content"].strip()
        meta_info["description"] = desc_text
        if len(desc_text) < 50:
            issues.append(Issue(
                category="SEO",
                severity="Medium",
                title="Meta description too short",
                detail=f"Meta description is only {len(desc_text)} characters. Aim for 120–160.",
            ))
        elif len(desc_text) > 165:
            issues.append(Issue(
                category="SEO",
                severity="Low",
                title="Meta description too long",
                detail=f"Meta description is {len(desc_text)} characters. Keep it under 165 to prevent truncation.",
            ))

    # ── 3. H1 Tag ──────────────────────────────────────────
    h1_tags = soup.find_all("h1")
    if not h1_tags:
        issues.append(Issue(
            category="SEO",
            severity="High",
            title="Missing H1 tag",
            detail="No H1 heading found on the page. Every page needs exactly one H1.",
        ))
        meta_info["h1"] = None
    elif len(h1_tags) > 1:
        issues.append(Issue(
            category="SEO",
            severity="Medium",
            title="Multiple H1 tags",
            detail=f"Found {len(h1_tags)} H1 tags. Use exactly one H1 per page.",
        ))
        meta_info["h1"] = h1_tags[0].get_text(strip=True)
    else:
        meta_info["h1"] = h1_tags[0].get_text(strip=True)

    # ── 4. Heading Hierarchy ───────────────────────────────
    heading_levels = []
    for level in range(1, 7):
        tags = soup.find_all(f"h{level}")
        heading_levels.append((level, len(tags)))

    meta_info["headings"] = {f"h{l}": c for l, c in heading_levels}

    # Check for skipped heading levels
    present = [l for l, c in heading_levels if c > 0]
    for i in range(len(present) - 1):
        if present[i + 1] - present[i] > 1:
            issues.append(Issue(
                category="SEO",
                severity="Low",
                title=f"Heading hierarchy skips H{present[i]+1}",
                detail=f"Heading jumps from H{present[i]} to H{present[i+1]}. Use sequential headings for accessibility and SEO.",
            ))
            break

    # ── 5. Canonical Tag ──────────────────────────────────
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if not canonical:
        issues.append(Issue(
            category="SEO",
            severity="Low",
            title="Missing canonical tag",
            detail="No <link rel='canonical'> found. Canonical tags prevent duplicate content issues.",
        ))
        meta_info["canonical"] = None
    else:
        meta_info["canonical"] = canonical.get("href", "")

    # ── 6. Open Graph Tags ────────────────────────────────
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_image = soup.find("meta", property="og:image")

    meta_info["og_title"] = og_title["content"] if og_title else None
    meta_info["og_description"] = og_desc["content"] if og_desc else None
    meta_info["og_image"] = og_image["content"] if og_image else None

    missing_og = []
    if not og_title:
        missing_og.append("og:title")
    if not og_desc:
        missing_og.append("og:description")
    if not og_image:
        missing_og.append("og:image")

    if missing_og:
        issues.append(Issue(
            category="SEO",
            severity="Medium",
            title="Incomplete Open Graph tags",
            detail=f"Missing Open Graph properties: {', '.join(missing_og)}. These affect how your page appears when shared on social media.",
        ))

    # ── 7. Robots Meta ───────────────────────────────────
    robots = soup.find("meta", attrs={"name": "robots"})
    if robots:
        content = robots.get("content", "").lower()
        if "noindex" in content:
            issues.append(Issue(
                category="SEO",
                severity="High",
                title="Page set to noindex",
                detail="The robots meta tag is set to 'noindex', preventing search engines from indexing this page.",
            ))

    # ── 8. Lang attribute ────────────────────────────────
    html_tag = soup.find("html")
    if html_tag and not html_tag.get("lang"):
        issues.append(Issue(
            category="Accessibility",
            severity="Medium",
            title="Missing lang attribute on <html>",
            detail="The <html> tag has no 'lang' attribute. This is important for screen readers and SEO.",
        ))

    # ── Score calculation ─────────────────────────────────
    # Start at 100 and deduct based on severity
    deductions = {"High": 20, "Medium": 10, "Low": 5}
    score = 100
    for issue in issues:
        score -= deductions.get(issue.severity, 5)
    score = max(0, min(100, score))

    return {
        "score": score,
        "issues": issues,
        "meta": meta_info,
    }
