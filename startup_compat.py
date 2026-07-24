"""Small startup helpers for Streamlit's long-lived Python process."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Iterable


def import_module_with_exports(
    module_name: str,
    required_exports: Iterable[str],
) -> ModuleType:
    """Import a module and refresh a stale cached copy when exports are missing."""
    required = tuple(required_exports)
    module = importlib.import_module(module_name)
    missing = [name for name in required if not hasattr(module, name)]
    if not missing:
        return module

    # Streamlit can rerun the entry-point after a deployment while retaining a
    # dependency module from the previous source revision in sys.modules.
    importlib.invalidate_caches()
    module = importlib.reload(module)
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ImportError(
            f"{module_name} is missing required exports after reload: "
            f"{missing_list}. Reboot the Streamlit app to refresh its checkout."
        )
    return module
