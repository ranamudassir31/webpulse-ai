"""
schemas.py — Pydantic Models
─────────────────────────────
All request/response shapes for the FastAPI app.

Pydantic does three things automatically:
  1. Validates incoming JSON (e.g. rejects bad URLs)
  2. Serialises outgoing data to clean JSON
  3. Powers the auto /docs page (Swagger UI)

Every model here appears in the interactive API docs at http://localhost:8000/docs
"""

from __future__ import annotations
from pydantic import BaseModel, HttpUrl, Field, field_validator
from typing import Optional
import time


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST models  (what the client sends TO the API)
# ─────────────────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    """
    Body sent by the frontend when starting a scan.

    Example JSON:
        { "url": "https://example.com" }
    """
    url: str = Field(
        ...,
        description="Full URL of the website to scan (must include https://)",
        examples=["https://example.com"],
        min_length=4,
        max_length=2048,
    )

    @field_validator("url")
    @classmethod
    def normalise_url(cls, v: str) -> str:
        """Auto-prepend https:// if the user forgot it."""
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        return v


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE models  (what the API sends BACK to the client)
# ─────────────────────────────────────────────────────────────────────────────

class IssueModel(BaseModel):
    """A single detected issue with its AI-generated suggestion."""
    category:   str = Field(description="Issue category: SEO | Accessibility | Bugs | Performance")
    severity:   str = Field(description="Severity level: High | Medium | Low")
    title:      str = Field(description="Short human-readable issue title")
    detail:     str = Field(description="Technical explanation of the issue")
    suggestion: str = Field(default="", description="AI-generated fix recommendation")


class ScoresModel(BaseModel):
    """Numeric quality scores for each category (0–100)."""
    overall:     int = Field(ge=0, le=100, description="Weighted overall quality score")
    seo:         int = Field(ge=0, le=100, description="SEO score")
    bugs:        int = Field(ge=0, le=100, description="Accessibility & code quality score")
    performance: int = Field(ge=0, le=100, description="Performance score")


class IssueCountsModel(BaseModel):
    """How many issues at each severity level."""
    High:   int = Field(default=0, ge=0)
    Medium: int = Field(default=0, ge=0)
    Low:    int = Field(default=0, ge=0)


class PageMetaModel(BaseModel):
    """Extracted page metadata."""
    title:          Optional[str] = None
    description:    Optional[str] = None
    h1:             Optional[str] = None
    canonical:      Optional[str] = None
    og_title:       Optional[str] = None
    og_description: Optional[str] = None
    og_image:       Optional[str] = None
    headings:       Optional[dict] = None


class PageStatsModel(BaseModel):
    """Numeric page statistics."""
    images_total:          Optional[int]   = None
    images_missing_alt:    Optional[int]   = None
    links_total:           Optional[int]   = None
    empty_links:           Optional[int]   = None
    inputs_total:          Optional[int]   = None
    page_size_kb:          Optional[float] = None
    response_time_ms:      Optional[float] = None
    render_blocking_scripts: Optional[int] = None
    external_stylesheets:  Optional[int]   = None
    external_scripts:      Optional[int]   = None
    images_lazy:           Optional[int]   = None


class ScanResponse(BaseModel):
    """
    Full scan result returned after a successful scan.
    This exact shape appears in the /docs Swagger UI.
    """
    scan_id:           int
    url:               str
    scanned_at:        float = Field(description="Unix timestamp of when scan ran")
    duration_ms:       float = Field(description="Total scan duration in milliseconds")
    status_code:       Optional[int] = Field(default=None, description="HTTP status code of the scanned page")
    scores:            ScoresModel
    issue_counts:      IssueCountsModel
    issues:            list[IssueModel]
    meta:              PageMetaModel
    stats:             PageStatsModel
    executive_summary: str
    error:             Optional[str] = Field(default=None, description="Error message if scan partially failed")


class ScanSummary(BaseModel):
    """
    Lightweight scan record used in the history list.
    Does NOT include the full issue list (for performance).
    """
    id:               int
    url:              str
    scanned_at:       float
    duration_ms:      float
    status:           str
    score_overall:    Optional[int] = None
    score_seo:        Optional[int] = None
    score_bugs:       Optional[int] = None
    score_performance: Optional[int] = None
    issues_high:      int = 0
    issues_medium:    int = 0
    issues_low:       int = 0


class HealthResponse(BaseModel):
    """Simple health check response."""
    status:  str = "ok"
    version: str = "2.0.0"
    message: str = "WebPulse AI is running"


class ErrorResponse(BaseModel):
    """Standard error shape returned on 4xx/5xx responses."""
    error:  str
    detail: Optional[str] = None
