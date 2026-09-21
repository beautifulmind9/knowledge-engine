from typing import Any, Protocol


class StateStore(Protocol):
    """Load and save a complete snapshot without interpreting domain records."""

    def load(self) -> dict[str, Any] | None: ...

    def save(self, state: dict[str, Any]) -> None: ...
