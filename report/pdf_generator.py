"""
report/pdf_generator.py  (fpdf2 upgraded version)
Generates a professional branded PDF. Falls back to plain text if fpdf2 missing.
"""
from __future__ import annotations
import time
from datetime import datetime

try:
    from fpdf import FPDF as _FPDF_BASE
    FPDF_AVAILABLE = True
except ImportError:
    _FPDF_BASE = object   # dummy base so class definition doesn't crash
    FPDF_AVAILABLE = False

# ── Colours (R, G, B) ────────────────────────────────────────────────────────
C_BG_DARK  = (15,  23,  42)
C_BG_LIGHT = (248, 250, 252)
C_BORDER   = (226, 232, 240)
C_ACCENT   = (79,  142, 247)
C_TEXT_DK  = (30,  41,  59)
C_TEXT_MD  = (100, 116, 139)
C_WHITE    = (255, 255, 255)
C_HIGH     = (220, 38,  38)
C_MEDIUM   = (217, 119, 6)
C_LOW      = (22,  163, 74)

def _score_color(s):
    return C_LOW if s >= 80 else C_MEDIUM if s >= 55 else C_HIGH

def _sev_color(sev):
    return {"High": C_HIGH, "Medium": C_MEDIUM, "Low": C_LOW}.get(sev, C_TEXT_MD)

# ── Public API ────────────────────────────────────────────────────────────────
def generate_pdf_report(scan_result: dict) -> bytes:
    if not FPDF_AVAILABLE:
        return _text_report(scan_result).encode("utf-8")

    url       = scan_result.get("url", "Unknown URL")
    scores    = scan_result.get("scores", {})
    issues    = scan_result.get("issues", [])
    meta      = scan_result.get("meta", {})
    stats     = scan_result.get("stats", {})
    summary   = scan_result.get("executive_summary", "")
    ts        = scan_result.get("scanned_at", time.time())
    scan_date = datetime.fromtimestamp(ts).strftime("%d %B %Y  -  %H:%M UTC")

    order = {"High": 0, "Medium": 1, "Low": 2}
    issues = sorted(issues, key=lambda x: order.get(x.get("severity","Low"), 3))

    pdf = _PDF(url=url, scan_date=scan_date)
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.add_page()

    _score_cards(pdf, scores)
    _heading(pdf, "Executive Summary")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*C_TEXT_DK)
    pdf.multi_cell(0, 6, summary or "No summary available.")
    pdf.ln(5)
    _heading(pdf, "Page Information")
    _page_info(pdf, meta, stats, scan_result.get("response_time_ms", 0))
    pdf.ln(3)
    _counts_bar(pdf, scan_result.get("issue_counts", {}), len(issues))
    pdf.ln(3)
    _heading(pdf, "Detected Issues  ({} total)".format(len(issues)))
    _issues_table(pdf, issues)
    suggestions = [i for i in issues if i.get("suggestion")]
    if suggestions:
        pdf.ln(3)
        _heading(pdf, "AI-Powered Recommendations")
        _recommendations(pdf, suggestions)

    return bytes(pdf.output())


# ── FPDF subclass ─────────────────────────────────────────────────────────────
class _PDF(_FPDF_BASE):
    def __init__(self, url, scan_date):
        if not FPDF_AVAILABLE:
            return
        super().__init__()
        self._url = url
        self._scan_date = scan_date
        self.set_margins(18, 18, 18)

    def header(self):
        self.set_fill_color(*C_BG_DARK)
        self.rect(0, 0, 210, 38, "F")
        self.set_y(9)
        self.set_x(18)
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(*C_WHITE)
        self.cell(50, 10, "WebPulse", ln=False)
        self.set_text_color(*C_ACCENT)
        self.cell(16, 10, " AI", ln=False)
        self.set_xy(18, 22)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 6, "Website Quality & Performance Audit Report", ln=False)
        self.set_xy(18, 9)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 6, "Audited: {}".format(self._url[:72]), align="R", ln=False)
        self.set_xy(18, 17)
        self.cell(0, 6, self._scan_date, align="R", ln=False)
        self.set_y(44)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*C_BORDER)
        self.line(18, self.get_y(), 192, self.get_y())
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*C_TEXT_MD)
        self.cell(0, 6,
            "WebPulse AI  -  {}  -  Page {}".format(self._scan_date, self.page_no()),
            align="C")


# ── Drawing helpers ───────────────────────────────────────────────────────────
def _heading(pdf, title: str):
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*C_BG_DARK)
    pdf.cell(0, 8, title, ln=True)
    pdf.set_draw_color(*C_ACCENT)
    pdf.set_line_width(0.6)
    pdf.line(18, pdf.get_y(), 100, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(4)

def _score_cards(pdf, scores: dict):
    cards = [
        ("Overall",       scores.get("overall",    0)),
        ("SEO",           scores.get("seo",         0)),
        ("Accessibility", scores.get("bugs",        0)),
        ("Performance",   scores.get("performance", 0)),
    ]
    y = pdf.get_y()
    for idx, (label, score) in enumerate(cards):
        x     = 18 + idx * 45
        color = _score_color(score)
        pdf.set_fill_color(*C_BG_LIGHT)
        pdf.set_draw_color(*C_BORDER)
        pdf.set_line_width(0.3)
        pdf.rect(x, y, 42, 30, "FD")
        pdf.set_fill_color(*color)
        pdf.rect(x, y, 42, 3, "F")
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(*color)
        pdf.set_xy(x, y + 5)
        pdf.cell(42, 12, str(score), align="C")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*C_TEXT_MD)
        pdf.set_xy(x, y + 18)
        pdf.cell(42, 6, "/100", align="C")
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*C_TEXT_DK)
        pdf.set_xy(x, y + 24)
        pdf.cell(42, 6, label, align="C")
    pdf.set_y(y + 36)
    pdf.ln(3)

def _page_info(pdf, meta: dict, stats: dict, rt: float):
    rows = [
        ("Page Title",       meta.get("title")       or "-- Missing --"),
        ("Meta Description", (meta.get("description") or "-- Missing --")[:90]),
        ("H1 Heading",       meta.get("h1")          or "-- Missing --"),
        ("Canonical URL",    meta.get("canonical")   or "-- Not set --"),
        ("Response Time",    "{} ms".format(rt) if rt else "--"),
        ("Page Size",        "{} KB".format(stats.get("page_size_kb","--"))),
        ("Images",           "{}  ({} missing alt)".format(
                             stats.get("images_total","--"),
                             stats.get("images_missing_alt",0))),
        ("Links",            str(stats.get("links_total","--"))),
        ("Ext. Scripts",     str(stats.get("external_scripts","--"))),
        ("Stylesheets",      str(stats.get("external_stylesheets","--"))),
    ]
    for i, (key, val) in enumerate(rows):
        bg = C_BG_LIGHT if i % 2 == 0 else C_WHITE
        pdf.set_fill_color(*bg)
        pdf.set_draw_color(*C_BORDER)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*C_TEXT_MD)
        pdf.cell(46, 7, "  {}".format(key), border="LTB", fill=True)
        pdf.set_font("Helvetica", "", 9)
        missing = "Missing" in val or "Not set" in val
        pdf.set_text_color(*C_HIGH if missing else C_TEXT_DK)
        pdf.cell(128, 7, "  {}".format(val), border="RTB", fill=True, ln=True)
    pdf.ln(2)

def _counts_bar(pdf, counts: dict, total: int):
    y = pdf.get_y()
    pdf.set_fill_color(*C_BG_LIGHT)
    pdf.set_draw_color(*C_BORDER)
    pdf.rect(18, y, 174, 12, "FD")
    pdf.set_xy(21, y + 2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*C_TEXT_DK)
    pdf.cell(32, 8, "Total issues: {}".format(total), ln=False)
    pdf.set_text_color(*C_HIGH)
    pdf.cell(38, 8, "High: {}".format(counts.get("High",0)), ln=False)
    pdf.set_text_color(*C_MEDIUM)
    pdf.cell(44, 8, "Medium: {}".format(counts.get("Medium",0)), ln=False)
    pdf.set_text_color(*C_LOW)
    pdf.cell(38, 8, "Low: {}".format(counts.get("Low",0)), ln=False)
    pdf.ln(16)

def _issues_table(pdf, issues: list):
    if not issues:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*C_LOW)
        pdf.cell(0, 8, "  No issues found -- great job!", ln=True)
        return
    pdf.set_fill_color(*C_BG_DARK)
    pdf.set_text_color(*C_WHITE)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(22, 7, "  Severity",   border=0, fill=True)
    pdf.cell(34, 7, "  Category",   border=0, fill=True)
    pdf.cell(0,  7, "  Issue Title",border=0, fill=True, ln=True)
    for idx, issue in enumerate(issues):
        sev    = issue.get("severity","Low")
        cat    = issue.get("category","")
        title  = issue.get("title","")
        row_bg = C_WHITE if idx % 2 == 0 else C_BG_LIGHT
        pdf.set_fill_color(*row_bg)
        pdf.set_draw_color(*C_BORDER)
        pdf.set_line_width(0.2)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_sev_color(sev))
        pdf.cell(22, 7, "  {}".format(sev), border="B", fill=True)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*C_TEXT_MD)
        pdf.cell(34, 7, "  {}".format(cat), border="B", fill=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*C_TEXT_DK)
        pdf.cell(0,  7, "  {}".format(title[:82]), border="B", fill=True, ln=True)
    pdf.ln(3)

def _recommendations(pdf, issues: list):
    for i, issue in enumerate(issues, 1):
        sev        = issue.get("severity","Low")
        title      = issue.get("title","")
        suggestion = issue.get("suggestion","")
        if not suggestion:
            continue
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_sev_color(sev))
        pdf.cell(8, 7, "{}.".format(i), ln=False)
        pdf.multi_cell(0, 7, title)
        y0 = pdf.get_y()
        pdf.set_x(24)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*C_TEXT_DK)
        pdf.set_fill_color(235, 243, 255)
        pdf.multi_cell(168, 5.5, suggestion, fill=True)
        bar_h = pdf.get_y() - y0
        pdf.set_fill_color(*C_ACCENT)
        pdf.rect(18, y0, 2.5, bar_h, "F")
        pdf.ln(4)


# ── Text fallback ─────────────────────────────────────────────────────────────
def _text_report(scan_result: dict) -> str:
    url    = scan_result.get("url","Unknown")
    scores = scan_result.get("scores",{})
    issues = scan_result.get("issues",[])
    now    = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines  = [
        "="*65,
        "  WebPulse AI  --  Website Audit Report",
        "="*65,
        "  URL:          {}".format(url),
        "  Date:         {}".format(now),
        "",
        "  SCORES",
        "  Overall:       {}/100".format(scores.get("overall","N/A")),
        "  SEO:           {}/100".format(scores.get("seo","N/A")),
        "  Accessibility: {}/100".format(scores.get("bugs","N/A")),
        "  Performance:   {}/100".format(scores.get("performance","N/A")),
        "",
        "  SUMMARY",
        "  {}".format(scan_result.get("executive_summary","")),
        "",
        "-"*65,
        "  ISSUES & AI RECOMMENDATIONS",
        "-"*65,
    ]
    for i, issue in enumerate(issues, 1):
        lines.append("\n  {}. [{}] {}".format(i, issue.get("severity","?"), issue.get("title","")))
        lines.append("     Category:  {}".format(issue.get("category","")))
        lines.append("     Detail:    {}".format(issue.get("detail","")))
        if issue.get("suggestion"):
            lines.append("     Fix:       {}".format(issue["suggestion"]))
    lines += ["","="*65,"  End of Report  --  WebPulse AI","="*65]
    return "\n".join(lines)
