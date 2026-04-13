"""
backend/app.py
PolyPi Pure — FastAPI Fullstack Backend v1.0
Serves the PolyPy DYTX runtime API + static frontend

Run:
    pip install -e ".[fullstack]"
    uvicorn backend.app:app --reload
    # OR via the installed CLI:
    polypi-serve
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Bootstrap: make the repo root importable so `import dytx` works
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dytx  # noqa: E402

# ---------------------------------------------------------------------------
# Boot DYTX in pure mode
# ---------------------------------------------------------------------------
dytx.init(mode="python", ide="pure")

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PolyPi Pure API",
    description="REST API wrapping the PolyPy DYTX runtime (PolyPi Pure v1.0)",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS — allow the dev frontend (Vite / live-server) to hit the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files — serve frontend/dist if it exists
# ---------------------------------------------------------------------------
FRONTEND_DIST = ROOT / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class DytxInitRequest(BaseModel):
    mode: str = "python"
    ide: str = "pure"
    target: str | None = None


class RunPoWRequest(BaseModel):
    proof: int  # 1-4


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    """Liveness check."""
    return {"status": "ok", "service": "polypi-pure-backend"}


@app.get("/api/runtime", response_model=dict)
def get_runtime() -> dict:
    """Return current DYTX runtime status."""
    return dytx.get_runtime_info()


@app.post("/api/runtime/init")
def reinit_runtime(req: DytxInitRequest) -> dict:
    """Re-initialise DYTX with the supplied parameters."""
    dytx.reset()
    try:
        dytx.init(mode=req.mode, ide=req.ide, target=req.target)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return dytx.get_runtime_info()


@app.get("/api/proofs")
def list_proofs() -> list:
    """List all available proof-of-work modules."""
    return [
        {"id": 1, "name": "Hello World",    "file": "proof_of_work_1_hello.py"},
        {"id": 2, "name": "LED Blink",      "file": "proof_of_work_2_led_blink.py"},
        {"id": 3, "name": "Web Output",     "file": "proof_of_work_3_web.py"},
        {"id": 4, "name": "3D Graphics",    "file": "proof_of_work_4_graphics.py"},
    ]


@app.post("/api/proofs/run")
def run_proof(req: RunPoWRequest) -> JSONResponse:
    """
    Execute a proof-of-work module in-process (pure Python simulation).
    Returns stdout lines captured during execution.
    """
    files = {
        1: ROOT / "proof_of_work_1_hello.py",
        2: ROOT / "proof_of_work_2_led_blink.py",
        3: ROOT / "proof_of_work_3_web.py",
        4: ROOT / "proof_of_work_4_graphics.py",
    }
    if req.proof not in files:
        raise HTTPException(status_code=404, detail=f"Proof #{req.proof} not found.")

    import io, contextlib  # noqa: E401

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            # Re-init for each run in pure mode
            dytx.reset()
            dytx.init(mode="python", ide="pure")
            spec = importlib.util.spec_from_file_location(
                f"pow_{req.proof}", str(files[req.proof])
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"proof": req.proof, "error": str(exc), "output": buf.getvalue()},
        )

    return JSONResponse(
        content={"proof": req.proof, "output": buf.getvalue()}
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root() -> str:
    """Fallback index when frontend/dist is not built yet."""
    html_path = ROOT / "frontend" / "index.html"
    if html_path.is_file():
        return html_path.read_text(encoding="utf-8")
    return """
<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><title>PolyPi Pure</title>
<style>body{font-family:monospace;background:#0d1117;color:#58a6ff;padding:2rem;}
h1{color:#f0883e;}a{color:#58a6ff;}</style></head>
<body>
<h1>PolyPi Pure v1.0</h1>
<p>Backend is running. Frontend not yet built.</p>
<p>→ <a href="/api/docs">Swagger UI</a></p>
<p>→ <a href="/api/redoc">ReDoc</a></p>
<p>→ <a href="/api/health">Health check</a></p>
<p>→ <a href="/api/runtime">Runtime info</a></p>
<p>→ <a href="/api/proofs">Proofs list</a></p>
</body></html>
    """


# ---------------------------------------------------------------------------
# CLI shim — required by pyproject.toml [project.scripts]
# polypi-serve = "backend.app:start"
# ---------------------------------------------------------------------------
def start() -> None:
    """Entry point for `polypi-serve` console script."""
    import uvicorn  # type: ignore[import]
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    start()
