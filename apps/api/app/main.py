import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
import fcntl
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError
from app.db.persistence import STORAGE_ROOT
from app.routers.health import router as health_router
from app.routers.knowledge import router as knowledge_router
from app.routers.gemini_batches import router as gemini_batches_router
from app.routers.libraries import router as libraries_router
from app.routers.sources import router as sources_router
from app.routers.workshop_output import router as workshop_output_router
from app.routers.workshops import router as workshops_router
from app.routers.outputs import router as outputs_router
from app.routers.control import router as control_router

@asynccontextmanager
async def lifespan(app):
    STORAGE_ROOT.mkdir(parents=True,exist_ok=True)
    with (STORAGE_ROOT / "server.lock").open("a") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another server is using this storage directory. Run exactly one worker.")
        yield

app=FastAPI(title="Knowledge Engine API",version="0.2.0",lifespan=lifespan)
# Single-owner local beta. This is not a multi-user authorization system.
app.add_middleware(TrustedHostMiddleware,allowed_hosts=["localhost","127.0.0.1","[::1]","testserver"])
request_lock=asyncio.Lock()

@app.middleware("http")
async def local_requests(request:Request,call_next):
    origin=request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        return JSONResponse({"detail":"Cross-origin access is disabled for this local private beta."},status_code=403)
    async with request_lock:
        response=await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Cache-Control"]="no-store"
    response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response

@app.exception_handler(ValueError)
async def value_error(request, error):
    return JSONResponse({"detail":str(error)},status_code=404 if "not found" in str(error).lower() else 400)

@app.exception_handler(RuntimeError)
async def runtime_error(request,error):
    return JSONResponse({"detail":str(error)},status_code=400)

@app.exception_handler(ValidationError)
async def invalid_ai_output(request,error):
    return JSONResponse({"detail":"Generated content failed schema validation. No output saved; retry explicitly."},status_code=422)

for router in (health_router,libraries_router,sources_router,knowledge_router,gemini_batches_router,workshops_router,workshop_output_router,outputs_router,control_router):
    app.include_router(router)

WEB_ROOT=Path(__file__).resolve().parents[2] / "web"
app.mount("/static",StaticFiles(directory=WEB_ROOT),name="static")

@app.get("/",include_in_schema=False)
def index():
    return FileResponse(WEB_ROOT / "index.html")
