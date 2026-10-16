import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import fcntl
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError
from app.db.persistence import STORAGE_ROOT
from app.persistence.factory import PERSISTENCE_MODE
from app.beta_access import BetaAccess, same_origin, router as beta_router
from app.deployment import public_host, local_https_forwarding_host, LOCAL_HOSTS, HostedHTTPSMiddleware
from app.services.performance_timing import start as _timing_start, emit as _timing_emit, operation_context

# Validate the gate before router imports can load hosted state.
beta_access = BetaAccess.from_environment(PERSISTENCE_MODE)
hosted_public_host = public_host(PERSISTENCE_MODE)
local_forwarding_host = local_https_forwarding_host(PERSISTENCE_MODE)
from app.routers.health import router as health_router
from app.routers.knowledge import router as knowledge_router
from app.routers.libraries import router as libraries_router
from app.routers.sources import router as sources_router
from app.routers.structure import router as structure_router
from app.routers.workshop_output import router as workshop_output_router
from app.routers.workshops import router as workshops_router
from app.routers.outputs import router as outputs_router
from app.routers.control import router as control_router

@asynccontextmanager
async def lifespan(app):
    if PERSISTENCE_MODE == "hosted":
        # Postgres CAS guards state writes; hosted artifacts need no local disk lock.
        yield
        return
    STORAGE_ROOT.mkdir(parents=True,exist_ok=True)
    with (STORAGE_ROOT / "server.lock").open("a") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another server is using this storage directory. Run exactly one worker.")
        yield

app=FastAPI(title="Knowledge Engine API",version="0.2.0",lifespan=lifespan)
app.state.beta_access = beta_access
# Single-owner local beta. This is not a multi-user authorization system.
allowed_hosts = [hosted_public_host] if hosted_public_host else LOCAL_HOSTS + (
    [local_forwarding_host] if local_forwarding_host else []
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts, www_redirect=False)
request_lock=asyncio.Lock()

@app.middleware("http")
async def local_requests(request:Request,call_next):
    timing_started = _timing_start()
    request_id=None
    async def invoke_route():
        nonlocal request_id
        path=request.url.path
        parts=path.split("/")
        suffix=parts[3] if len(parts)>3 else None
        source_id=parts[2] if len(parts)>2 and parts[1]=="sources" and parts[2]!="summaries" else None
        categories={"interpret":"material_preparation_request","summary":"source_summary_request",
                    "summaries":"library_source_summaries","process":"source_read_request",
                    "extract":"source_extraction_request","chunk":"source_chunk_request",
                    "upload":"source_upload_request"}
        operation="library_source_summaries" if path=="/sources/summaries" else categories.get(suffix)
        if path == "/workshops/generate":
            operation = "workshop_generate_request"
        if operation:
            try:
                request_id=uuid4().hex
            except Exception:
                request_id=None
            request.state.request_id = request_id
            context={"request_id":request_id,"operation_category":operation}
            if source_id:
                context["source_id"]=source_id
            with operation_context(**context):
                return await call_next(request)
        return await call_next(request)
    if not same_origin(request, https_forwarding_host=local_forwarding_host):
        response = JSONResponse({"detail":"Cross-origin access is disabled for this local private beta."}, status_code=403)
    else:
        gate = request.app.state.beta_access
        response = gate.enforce(request) if gate is not None else None
        if response is None:
            if request.method == "GET" and request.url.path == "/health":
                # Pure process liveness must remain responsive during provider work.
                response=await invoke_route()
            else:
                async with request_lock:
                    response=await invoke_route()
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Cache-Control"]="no-store"
    response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    path=request.url.path
    event=("material_preparation_request" if path.endswith("/interpret") else
           "source_create_request" if path=="/sources" and request.method=="POST" else
           "source_upload_request" if path.endswith("/upload") else
           "source_read_request" if path.endswith("/process") else
           "source_extraction_request_total" if path.endswith("/extract") else
           "source_chunk_request_total" if path.endswith("/chunk") else None)
    pieces=path.split("/")
    source_id=pieces[2] if len(pieces)>2 and pieces[1]=="sources" else None
    if event:
        _timing_emit(event,timing_started,result="success" if response.status_code<400 else "http_error",method=request.method,endpoint=path,source_id=source_id,request_id=request_id)
    return response

# Outer hosted ingress validation also covers early authentication responses.
if hosted_public_host is not None:
    app.add_middleware(HostedHTTPSMiddleware, host=hosted_public_host)

@app.exception_handler(ValueError)
async def value_error(request, error):
    return JSONResponse({"detail":str(error)},status_code=404 if "not found" in str(error).lower() else 400)

@app.exception_handler(RuntimeError)
async def runtime_error(request,error):
    return JSONResponse({"detail":str(error)},status_code=400)

@app.exception_handler(ValidationError)
async def invalid_ai_output(request,error):
    return JSONResponse({"detail":"Generated content failed schema validation. No output saved; retry explicitly."},status_code=422)

for router in (beta_router,health_router,libraries_router,sources_router,structure_router,knowledge_router,workshops_router,workshop_output_router,outputs_router,control_router):
    app.include_router(router)

WEB_ROOT=Path(__file__).resolve().parents[2] / "web"
app.mount("/static",StaticFiles(directory=WEB_ROOT),name="static")

@app.get("/",include_in_schema=False)
def index():
    return FileResponse(WEB_ROOT / "index.html")
