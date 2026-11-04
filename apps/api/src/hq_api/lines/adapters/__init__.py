"""Step adapters (contract §30.2); each module registers one kind.

`load()` imports every module of this package once (the engine, the worker
and the routes call it before they look a kind up in `base.REGISTRY`). A
module that fails to import is logged and skipped: one broken adapter never
stops the others; a step of its kind then fails with a plain reason. Tests
call `load()` first and then register their fakes over the real adapters.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil

log = logging.getLogger("hq_api.lines.adapters")

_status: dict[str, str] = {}


def load() -> dict[str, str]:
    """{module: "ok" | "failed: <error type>"}; imports only once per process."""
    if _status:
        return dict(_status)
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{__name__}.{info.name}")
        except Exception as exc:  # noqa: BLE001 - one adapter never stops the others
            log.warning(
                "line adapter not loaded", extra={"module": info.name, "error": type(exc).__name__}
            )
            _status[info.name] = f"failed: {type(exc).__name__}"
            continue
        _status[info.name] = "ok"
    _status.setdefault("_", "ok")  # loaded, even with no module at all
    return dict(_status)
