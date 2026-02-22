"""Backward compatibility — imports from crunch_config.py.

The canonical module is `coordinator_node.crunch_config`. This shim keeps
existing `from coordinator_node.contracts import CrunchContract` working.

**Important**: ``CrunchContract`` is resolved via ``config_loader`` so that
operator overrides in ``runtime_definitions`` are auto-discovered.  Direct
class references (``CrunchConfig``) are still re-exported for subclassing.
"""
from coordinator_node.crunch_config import *  # noqa: F401,F403
from coordinator_node.crunch_config import CrunchConfig


def __getattr__(name: str):
    """Lazy attribute access — resolve CrunchContract through the config loader.

    This means ``from coordinator_node.contracts import CrunchContract`` returns
    the *loaded* (possibly operator-customized) config instance, not the bare
    engine default class.
    """
    if name == "CrunchContract":
        from coordinator_node.config_loader import load_config
        return load_config()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
