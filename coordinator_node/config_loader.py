"""Config loader — resolve the operator's CrunchConfig at startup.

Workers call `load_config()` instead of `CrunchConfig()`. This tries
to import the operator's customized config from `runtime_definitions`,
falling back to the engine default.

Resolution order:
1. `CRUNCH_CONFIG_MODULE` env var (e.g. `my_package.config:MyConfig`)
2. `runtime_definitions.contracts:CrunchConfig` (standard operator override)
3. `runtime_definitions.contracts:CrunchContract` (backward compat alias)
4. `runtime_definitions.crunch_config:CrunchConfig` (new-style name)
5. `coordinator_node.crunch_config:CrunchConfig` (engine default)
"""
from __future__ import annotations

import importlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_cached_config: Any = None


def load_config() -> Any:
    """Load and cache the CrunchConfig instance.

    Returns a CrunchConfig (or subclass) from the first successful source.
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    config = _resolve_config()
    _cached_config = config
    return config


# Backward compat alias
load_contract = load_config


def _resolve_config() -> Any:
    """Try each config source in priority order."""

    # 1. Explicit env var
    explicit = os.getenv("CRUNCH_CONFIG_MODULE", "").strip()
    if not explicit:
        # Backward compat
        explicit = os.getenv("CONTRACT_MODULE", "").strip()
    if explicit:
        config = _try_load(explicit)
        if config is not None:
            logger.info("Loaded config from CRUNCH_CONFIG_MODULE=%s", explicit)
            return config
        logger.warning("CRUNCH_CONFIG_MODULE=%s failed to load, trying fallbacks", explicit)

    # 2. Operator's runtime_definitions (try multiple conventions)
    for path in [
        "runtime_definitions.contracts:CrunchConfig",
        "runtime_definitions.contracts:CrunchContract",  # backward compat
        "runtime_definitions.contracts:CONTRACT",
        "runtime_definitions.crunch_config:CrunchConfig",
    ]:
        config = _try_load(path)
        if config is not None:
            logger.info("Loaded config from %s", path)
            return config

    # 3. Engine default
    from coordinator_node.crunch_config import CrunchConfig
    logger.info("Using default CrunchConfig (no operator override found)")
    return CrunchConfig()


def _try_load(path: str) -> Any:
    """Try to import a config from a dotted path.

    Supports two forms:
    - `module.path:ClassName` — instantiates the class
    - `module.path:INSTANCE` — uses the object directly
    """
    try:
        if ":" in path:
            module_name, attr_name = path.rsplit(":", 1)
        else:
            module_name = path
            attr_name = "CrunchConfig"

        module = importlib.import_module(module_name)
        target = getattr(module, attr_name)

        # If it's a class, instantiate it
        if isinstance(target, type):
            return target()

        # If it's already an instance, use it directly
        return target

    except (ImportError, AttributeError):
        return None
    except Exception as exc:
        logger.debug("Failed to load config from %s: %s", path, exc)
        return None


def reset_cache() -> None:
    """Clear the cached config (for testing)."""
    global _cached_config
    _cached_config = None
