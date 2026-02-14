"""Backward compatibility — imports from crunch_config.py.

The canonical module is `coordinator_node.crunch_config`. This shim keeps
existing `from coordinator_node.contracts import CrunchContract` working.
`CrunchContract` is an alias for `CrunchConfig`.
"""
from coordinator_node.crunch_config import *  # noqa: F401,F403
from coordinator_node.crunch_config import CrunchConfig

# Backward-compat alias
CrunchContract = CrunchConfig
