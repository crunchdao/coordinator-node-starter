"""Contract loader — resolve the operator's CrunchContract at startup.

Workers call `load_contract()` instead of `CrunchContract()`. This tries
to import the operator's customized contract from `runtime_definitions`,
falling back to the engine default.

Resolution order:
1. `CONTRACT_MODULE` env var (e.g. `my_package.contracts:MyContract`)
2. `runtime_definitions.contracts:CrunchContract` (standard operator override)
3. `coordinator_node.contracts:CrunchContract` (engine default)
"""
from __future__ import annotations

import importlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_cached_contract: Any = None


def load_contract() -> Any:
    """Load and cache the CrunchContract instance.

    Returns a CrunchContract (or subclass) from the first successful source.
    """
    global _cached_contract
    if _cached_contract is not None:
        return _cached_contract

    contract = _resolve_contract()
    _cached_contract = contract
    return contract


def _resolve_contract() -> Any:
    """Try each contract source in priority order."""

    # 1. Explicit env var
    explicit = os.getenv("CONTRACT_MODULE", "").strip()
    if explicit:
        contract = _try_load(explicit)
        if contract is not None:
            logger.info("Loaded contract from CONTRACT_MODULE=%s", explicit)
            return contract
        logger.warning("CONTRACT_MODULE=%s failed to load, trying fallbacks", explicit)

    # 2. Operator's runtime_definitions
    for path in [
        "runtime_definitions.contracts:CrunchContract",
        "runtime_definitions.contracts:CONTRACT",
    ]:
        contract = _try_load(path)
        if contract is not None:
            logger.info("Loaded contract from %s", path)
            return contract

    # 3. Engine default
    from coordinator_node.contracts import CrunchContract
    logger.info("Using default CrunchContract (no operator override found)")
    return CrunchContract()


def _try_load(path: str) -> Any:
    """Try to import a contract from a dotted path.

    Supports two forms:
    - `module.path:ClassName` — instantiates the class
    - `module.path:INSTANCE` — uses the object directly
    """
    try:
        if ":" in path:
            module_name, attr_name = path.rsplit(":", 1)
        else:
            module_name = path
            attr_name = "CrunchContract"

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
        logger.debug("Failed to load contract from %s: %s", path, exc)
        return None


def reset_cache() -> None:
    """Clear the cached contract (for testing)."""
    global _cached_contract
    _cached_contract = None
