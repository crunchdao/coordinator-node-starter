"""Backward compatibility — use config_loader instead."""
from coordinator_node.config_loader import *  # noqa: F401,F403
from coordinator_node.config_loader import load_config as load_contract  # noqa: F401
from coordinator_node.config_loader import reset_cache  # noqa: F401
