"""Tests for config_loader — resolve operator's CrunchConfig."""
from __future__ import annotations

import os
import sys
import types
import unittest

from coordinator_node.config_loader import load_config, reset_cache, _try_load


class TestTryLoad(unittest.TestCase):
    def test_loads_class_and_instantiates(self):
        mod = types.ModuleType("_test_config_mod")
        from coordinator_node.crunch_config import CrunchConfig

        class CustomConfig(CrunchConfig):
            pass

        mod.CrunchConfig = CustomConfig
        sys.modules["_test_config_mod"] = mod

        try:
            result = _try_load("_test_config_mod:CrunchConfig")
            self.assertIsInstance(result, CustomConfig)
        finally:
            del sys.modules["_test_config_mod"]

    def test_loads_instance_directly(self):
        mod = types.ModuleType("_test_config_inst")
        from coordinator_node.crunch_config import CrunchConfig

        instance = CrunchConfig(metrics=["ic"])
        mod.CONTRACT = instance
        sys.modules["_test_config_inst"] = mod

        try:
            result = _try_load("_test_config_inst:CONTRACT")
            self.assertIs(result, instance)
            self.assertEqual(result.metrics, ["ic"])
        finally:
            del sys.modules["_test_config_inst"]

    def test_missing_module_returns_none(self):
        result = _try_load("nonexistent_module_xyz:CrunchConfig")
        self.assertIsNone(result)

    def test_missing_attribute_returns_none(self):
        result = _try_load("coordinator_node.crunch_config:NonExistentClass")
        self.assertIsNone(result)


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        reset_cache()

    def tearDown(self):
        reset_cache()
        os.environ.pop("CRUNCH_CONFIG_MODULE", None)
        os.environ.pop("CONTRACT_MODULE", None)

    def test_falls_back_to_engine_default(self):
        config = load_config()
        from coordinator_node.crunch_config import CrunchConfig
        self.assertIsInstance(config, CrunchConfig)

    def test_explicit_env_var(self):
        mod = types.ModuleType("_test_explicit")
        from coordinator_node.crunch_config import CrunchConfig

        class ExplicitConfig(CrunchConfig):
            metrics: list[str] = ["custom_metric"]

        mod.ExplicitConfig = ExplicitConfig
        sys.modules["_test_explicit"] = mod
        os.environ["CRUNCH_CONFIG_MODULE"] = "_test_explicit:ExplicitConfig"

        try:
            config = load_config()
            self.assertIsInstance(config, ExplicitConfig)
            self.assertEqual(config.metrics, ["custom_metric"])
        finally:
            del sys.modules["_test_explicit"]

    def test_backward_compat_contract_module_env(self):
        mod = types.ModuleType("_test_compat")
        from coordinator_node.crunch_config import CrunchConfig

        class CompatConfig(CrunchConfig):
            metrics: list[str] = ["compat"]

        mod.CompatConfig = CompatConfig
        sys.modules["_test_compat"] = mod
        os.environ["CONTRACT_MODULE"] = "_test_compat:CompatConfig"

        try:
            config = load_config()
            self.assertIsInstance(config, CompatConfig)
        finally:
            del sys.modules["_test_compat"]

    def test_caches_result(self):
        c1 = load_config()
        c2 = load_config()
        self.assertIs(c1, c2)

    def test_reset_cache_works(self):
        c1 = load_config()
        reset_cache()
        c2 = load_config()
        self.assertIsNot(c1, c2)


class TestBackwardCompat(unittest.TestCase):
    """Verify old import paths still work."""

    def test_import_from_contracts(self):
        from coordinator_node.contracts import CrunchContract
        from coordinator_node.crunch_config import CrunchConfig
        self.assertIs(CrunchContract, CrunchConfig)

    def test_import_load_contract(self):
        from coordinator_node.contract_loader import load_contract
        from coordinator_node.config_loader import load_config
        # Both should be the same function
        self.assertIs(load_contract, load_config)


if __name__ == "__main__":
    unittest.main()
