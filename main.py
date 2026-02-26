"""
main.py  —  WebPulse AI  FastAPI Server v3.1 (Render Ready)
────────────────────────────────────────────────────────────
WHAT CHANGED IN v3.1 (Render deployment update):
  - Reads PORT from environment variable (Render requires this)
  - Reads ENVIRONMENT variable to know if running in production
  - Startup log shows the live URL when deployed
  - Graceful handling if static folder is missing on server
  - All previous features (Claude, async, /docs) unchanged

HOW TO RUN LOCALLY:
  uvicorn main:app --reload --port 8000

HOW RENDER RUNS IT:
  uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2

URLS:
  http://localhost:8000        →  Dashboard
  http://localhost:8000/docs   →  Swagger API docs
  http://localhost:8000/redoc  →  ReDoc API reference
  /api/health                  →  Health check (Render pings this)
  /api/ai-status               →  Claude AI status
  /api/scan        POST        →  Run a scan
  /api/scans       GET         →  Scan history
  /api/scan/{id}   GET/DELETE  →  Single scan
  /api/report/{id} GET         →  Download PDF
  /api/stats       GET         →  Aggregate stats
"""
from __future__ import annotations
import os, time, logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

# ── Load .env file (local dev only — Render uses its own env vars) ────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    _dotenv_loaded = True
except ImportError:
    _dotenv_loaded = False

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from schemas import (
    ScanRequest, ScanResponse, ScanSummary,
    HealthResponse, ErrorResponse,
    ScoresModel, IssueCountsModel, PageMetaModel,
    PageStatsModel, IssueModel,
)
from core_async import run_scan_async
from database  import init_db, save_scan, get_recent_scans, get_scan_by_id

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("webpulse")

# ── Environment ───────────────────────────────────────────────────────────────
# Render sets ENVIRONMENT=production automatically via render.yaml
IS_PRODUCTION = os.environ.get("ENVIRONMENT", "development") == "production"

# Render injects PORT automatically — we read it here for the startup log
PORT = int(os.environ.get("PORT", 8000))


# ── Startup / Shutdown ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 55)
    log.info("  WebPulse AI v3.1 starting ...")
    log.info("  Environment:  {}".format("PRODUCTION (Render)" if IS_PRODUCTION else "local dev"))

    # Initialise database
    init_db()
    log.info("  Database:     ready")

    # Claude AI status
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    claude_enabled = os.environ.get("CLAUDE_ENABLED", "true").lower() != "false"
    if api_key and api_key != "sk-ant-your-key-goes-here" and claude_enabled:
        log.info("  Claude AI:    ENABLED  (live suggestions active)")
    else:
        log.info("  Claude AI:    DISABLED (static suggestions)")
        if not api_key:
            log.info("  Tip: set ANTHROPIC_API_KEY in Render dashboard to enable Claude")

    # Show correct URL depending on environment
    if IS_PRODUCTION:
        log.info("  Live at:      your Render URL (check Render dashboard)")
    else:
        log.info("  Local URL:    http://localhost:{}".format(PORT))
        log.info("  API Docs:     http://localhost:{}/docs".format(PORT))

    log.info("=" * 55)
    yield
    log.info("WebPulse AI shutting down.")


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="WebPulse AI",
    description="""
## ⚡ WebPulse AI — Website Quality & Performance Scanner

Automatically audit any website for **SEO**, **accessibility**, and **performance** issues.
Receive **AI-powered fix recommendations** and download a branded **PDF report**.

### Endpoints
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/scan` | Run a full website audit |
| `GET` | `/api/scans` | List recent scan history |
| `GET` | `/api/scan/{id}` | Get a single scan result |
| `GET` | `/api/report/{id}` | Download PDF report |
| `DELETE` | `/api/scan/{id}` | Delete a scan |
| `GET` | `/api/stats` | Aggregate statistics |
| `GET` | `/api/ai-status` | Check if Claude AI is active |
| `GET` | `/api/health` | Health check |
    """,
    version="3.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten to your domain in production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request timing log ────────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    ms = round((time.time() - t0) * 1000)
    # Skip logging static file requests to keep logs clean
    if not request.url.path.startswith("/static"):
        log.info("{:6}  {:<40}  {}  {}ms".format(
            request.method, str(request.url.path), response.status_code, ms))
    return response


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check",
    description="Render pings this every 30 seconds to confirm the app is running.",
)
async def health_check():
    return HealthResponse()


@app.get(
    "/api/ai-status",
    tags=["System"],
    summary="Check if Claude AI is active",
    description="Returns whether your ANTHROPIC_API_KEY is configured in the environment.",
)
async def ai_status():
    api_key       = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    claude_env    = os.environ.get("CLAUDE_ENABLED", "true").lower() != "false"
    is_active     = bool(api_key and api_key != "sk-ant-your-key-goes-here" and claude_env)
    return {
        "ai_enabled":    is_active,
        "mode":          "claude" if is_active else "static",
        "model":         os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        "anthropic_sdk": _sdk_available(),
        "environment":   "production" if IS_PRODUCTION else "development",
        "message": (
            "Claude AI is active. Suggestions are generated live for each website."
            if is_active else
            "Using static suggestions. Add ANTHROPIC_API_KEY in Render dashboard to enable Claude."
        ),
    }


@app.get(
    "/api/stats",
    tags=["System"],
    summary="Aggregate statistics",
    description="Returns total scans, average score, and issue counts across all history.",
)
async def get_stats():
    from database import get_connection
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        avg   = conn.execute("SELECT AVG(score_overall) FROM scans WHERE score_overall IS NOT NULL").fetchone()[0]
        high  = conn.execute("SELECT SUM(issues_high)   FROM scans").fetchone()[0]
        med   = conn.execute("SELECT SUM(issues_medium) FROM scans").fetchone()[0]
        low_c = conn.execute("SELECT SUM(issues_low)    FROM scans").fetchone()[0]
    return {
        "total_scans":   total or 0,
        "average_score": round(avg, 1) if avg else 0,
        "total_issues":  {"High": high or 0, "Medium": med or 0, "Low": low_c or 0},
    }


# ─────────────────────────────────────────────────────────────────────────────
# SCANNER ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/scan",
    response_model=ScanResponse,
    tags=["Scanner"],
    summary="Scan a website",
    description="""
Run a full quality audit on any URL.

Checks performed:
- **SEO**: title, meta description, H1, Open Graph, canonical, robots, lang
- **Accessibility**: alt text, viewport, form labels, empty links, deprecated tags
- **Performance**: HTTPS, response time, page size, render-blocking scripts, lazy loading

Returns scores (0–100), issues sorted by severity, AI suggestions, and page metadata.
    """,
    responses={
        400: {"model": ErrorResponse, "description": "Missing or invalid URL"},
        422: {"model": ErrorResponse, "description": "Request validation error"},
        500: {"model": ErrorResponse, "description": "Scan failed unexpectedly"},
    },
)
async def scan_website(body: ScanRequest):
    url = body.url
    log.info("Scan started   url={}".format(url))
    t_start = time.time()

    result      = await run_scan_async(url)
    duration_ms = (time.time() - t_start) * 1000
    result["duration_ms"] = round(duration_ms, 1)

    scan_id        = save_scan(url, duration_ms, result)
    result["scan_id"] = scan_id

    log.info("Scan complete  id={}  score={}  issues={}  mode={}  {:.0f}ms".format(
        scan_id,
        result.get("scores", {}).get("overall", "?"),
        len(result.get("issues", [])),
        "claude" if result.get("ai_powered") else "static",
        duration_ms,
    ))

    return _build_response(result)


# ─────────────────────────────────────────────────────────────────────────────
# HISTORY ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/api/scans",
    response_model=list[ScanSummary],
    tags=["History"],
    summary="List recent scans",
    description="Returns the 20 most recent scans (lightweight — no full issue lists).",
)
async def list_scans():
    return get_recent_scans(20)


@app.get(
    "/api/scan/{scan_id}",
    response_model=ScanResponse,
    tags=["History"],
    summary="Get a single scan by ID",
    description="Returns the full result including all issues and AI suggestions.",
    responses={404: {"model": ErrorResponse}},
)
async def get_scan(scan_id: int):
    scan = get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan {} not found".format(scan_id))
    result = scan.get("result", {})
    result["scan_id"] = scan["id"]
    return _build_response(result)


@app.delete(
    "/api/scan/{scan_id}",
    tags=["History"],
    summary="Delete a scan",
    description="Permanently remove a scan from history.",
    status_code=204,
    responses={404: {"model": ErrorResponse}},
)
async def delete_scan(scan_id: int):
    from database import get_connection
    if not get_scan_by_id(scan_id):
        raise HTTPException(status_code=404, detail="Scan {} not found".format(scan_id))
    with get_connection() as conn:
        conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    log.info("Deleted scan {}".format(scan_id))
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────────────────────
# REPORT ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/api/report/{scan_id}",
    tags=["Reports"],
    summary="Download PDF audit report",
    description="""
Download a professional branded PDF for a completed scan.

Includes:
- Score cards for all 4 categories
- Full issue list sorted by severity
- AI-powered fix recommendations
- Page metadata table
- Branded header and footer on every page
    """,
    responses={
        200: {"content": {"application/pdf": {}, "text/plain": {}}},
        404: {"model": ErrorResponse},
    },
)
async def download_report(scan_id: int):
    scan = get_scan_by_id(scan_id)
    if not scan or not scan.get("result"):
        raise HTTPException(status_code=404, detail="Scan {} not found".format(scan_id))

    from report.pdf_generator import generate_pdf_report, FPDF_AVAILABLE
    result    = scan["result"]
    pdf_bytes = generate_pdf_report(result)
    domain    = urlparse(result.get("url", "site")).netloc.replace(".", "_") or "report"

    if FPDF_AVAILABLE:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="webpulse_{}.pdf"'.format(domain)},
        )
    else:
        return Response(
            content=pdf_bytes,
            media_type="text/plain",
            headers={"Content-Disposition": 'attachment; filename="webpulse_{}.txt"'.format(domain)},
        )


# ─────────────────────────────────────────────────────────────────────────────
# STATIC FILE SERVING  (the frontend dashboard)
# ─────────────────────────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"

# Only mount static files if the folder exists
# (prevents crash if somehow the folder is missing on the server)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    log.debug("Static files mounted from {}".format(STATIC_DIR))


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    # Fallback if static folder missing — show a helpful JSON message
    return JSONResponse({
        "app":     "WebPulse AI v3.1",
        "status":  "running",
        "message": "Dashboard not found. API is available at /docs",
        "docs":    "/docs",
    })


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    """
    Catch-all route for the single-page app.
    Any URL that isn't an API route gets the index.html
    so the frontend router can handle it.
    """
    # Don't swallow API 404s
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")

    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Not found")


# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _build_response(result: dict) -> ScanResponse:
    """Convert a raw scan result dict into a validated Pydantic ScanResponse."""
    scores = result.get("scores", {})
    counts = result.get("issue_counts", {})
    meta   = result.get("meta", {})
    stats  = result.get("stats", {})

    return ScanResponse(
        scan_id           = result.get("scan_id", 0),
        url               = result.get("url", ""),
        scanned_at        = result.get("scanned_at", time.time()),
        duration_ms       = result.get("duration_ms", 0),
        status_code       = result.get("status_code"),
        scores            = ScoresModel(
            overall     = scores.get("overall", 0),
            seo         = scores.get("seo", 0),
            bugs        = scores.get("bugs", 0),
            performance = scores.get("performance", 0),
        ),
        issue_counts      = IssueCountsModel(
            High   = counts.get("High", 0),
            Medium = counts.get("Medium", 0),
            Low    = counts.get("Low", 0),
        ),
        issues            = [
            IssueModel(
                category   = i.get("category", ""),
                severity   = i.get("severity", "Low"),
                title      = i.get("title", ""),
                detail     = i.get("detail", ""),
                suggestion = i.get("suggestion", ""),
            )
            for i in result.get("issues", [])
        ],
        meta              = PageMetaModel(
            title          = meta.get("title"),
            description    = meta.get("description"),
            h1             = meta.get("h1"),
            canonical      = meta.get("canonical"),
            og_title       = meta.get("og_title"),
            og_description = meta.get("og_description"),
            og_image       = meta.get("og_image"),
            headings       = meta.get("headings"),
        ),
        stats             = PageStatsModel(
            images_total             = stats.get("images_total"),
            images_missing_alt       = stats.get("images_missing_alt"),
            links_total              = stats.get("links_total"),
            empty_links              = stats.get("empty_links"),
            inputs_total             = stats.get("inputs_total"),
            page_size_kb             = stats.get("page_size_kb"),
            response_time_ms         = result.get("response_time_ms"),
            render_blocking_scripts  = stats.get("render_blocking_scripts"),
            external_stylesheets     = stats.get("external_stylesheets"),
            external_scripts         = stats.get("external_scripts"),
            images_lazy              = stats.get("images_lazy"),
        ),
        executive_summary = result.get("executive_summary", ""),
        error             = result.get("error"),
    )


def _sdk_available() -> bool:
    """Check if the Anthropic SDK is installed."""
    try:
        import anthropic
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# LOCAL DEV ENTRY POINT
# Run with:  python main.py
# Or better: uvicorn main:app --reload --port 8000
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host    = "0.0.0.0",
        port    = PORT,
        reload  = True,        # auto-restart on file save (dev only)
        log_level = "info",
    )
