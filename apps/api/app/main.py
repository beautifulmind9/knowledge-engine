from fastapi import FastAPI

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
