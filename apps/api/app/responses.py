"""HTTP response lifetimes for materialized artifacts."""
from pathlib import Path

from starlette.responses import FileResponse
from starlette.types import Receive, Scope, Send

from app.persistence.contracts import ArtifactStore


class ArtifactFileResponse(FileResponse):
    def __init__(self, path: Path, store: ArtifactStore, *, filename: str):
        super().__init__(path=path, filename=filename)
        self._artifact_store = store

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        original_path = self.path
        with self._artifact_store.materialize(original_path) as local_path:
            self.path = local_path
            try:
                await super().__call__(scope, receive, send)
            finally:
                self.path = original_path
