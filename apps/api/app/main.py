from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi import FastAPI

from app.routers.knowledge import router as knowledge_router
from app.routers.health import router as health_router
from app.routers.libraries import router as libraries_router
from app.routers.sources import router as sources_router
from app.routers.workshops import router as workshops_router

app = FastAPI(
    title="Knowledge Engine API",
    version="0.1.0"
)

app.include_router(health_router)
app.include_router(libraries_router)
app.include_router(sources_router)
app.include_router(workshops_router)

app.include_router(knowledge_router)

# The first release is a single-owner local application. Mutations from other
# browser origins are rejected. Bind to loopback; add real identity before hosting.
@app.middleware("http")
async def same_origin_writes(request, call_next):
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if origin.rstrip("/") != expected:
            return JSONResponse({"detail": "Cross-origin writes are not allowed."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers["Cache-Control"] = "no-store"
    return response

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"
app.mount("/workspace", StaticFiles(directory=WEB_ROOT), name="workspace")

@app.get("/", include_in_schema=False)
def workspace():
    return FileResponse(WEB_ROOT / "index.html")
