"""Backward compatibility — canonical module is crunch_config.py."""
from runtime_definitions.crunch_config import *  # noqa: F401,F403
from runtime_definitions.crunch_config import CrunchConfig  # noqa: F401

# Backward compat alias
CrunchContract = CrunchConfig
