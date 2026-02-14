"""Tests for contract_loader — resolve operator's CrunchContract."""
from __future__ import annotations

import os
import sys
import types
import unittest

from coordinator_node.contract_loader import load_contract, reset_cache, _try_load


class TestTryLoad(unittest.TestCase):
    def test_loads_class_and_instantiates(self):
        mod = types.ModuleType("_test_contract_mod")
        from coordinator_node.contracts import CrunchContract

        class CustomContract(CrunchContract):
            pass

        mod.CrunchContract = CustomContract
        sys.modules["_test_contract_mod"] = mod

        try:
            result = _try_load("_test_contract_mod:CrunchContract")
            self.assertIsInstance(result, CustomContract)
        finally:
            del sys.modules["_test_contract_mod"]

    def test_loads_instance_directly(self):
        mod = types.ModuleType("_test_contract_inst")
        from coordinator_node.contracts import CrunchContract

        instance = CrunchContract(metrics=["ic"])
        mod.CONTRACT = instance
        sys.modules["_test_contract_inst"] = mod

        try:
            result = _try_load("_test_contract_inst:CONTRACT")
            self.assertIs(result, instance)
            self.assertEqual(result.metrics, ["ic"])
        finally:
            del sys.modules["_test_contract_inst"]

    def test_missing_module_returns_none(self):
        result = _try_load("nonexistent_module_xyz:CrunchContract")
        self.assertIsNone(result)

    def test_missing_attribute_returns_none(self):
        result = _try_load("coordinator_node.contracts:NonExistentClass")
        self.assertIsNone(result)


class TestLoadContract(unittest.TestCase):
    def setUp(self):
        reset_cache()

    def tearDown(self):
        reset_cache()
        os.environ.pop("CONTRACT_MODULE", None)

    def test_falls_back_to_engine_default(self):
        # No runtime_definitions on path, no env var
        contract = load_contract()
        from coordinator_node.contracts import CrunchContract
        self.assertIsInstance(contract, CrunchContract)

    def test_explicit_env_var(self):
        mod = types.ModuleType("_test_explicit")
        from coordinator_node.contracts import CrunchContract

        class ExplicitContract(CrunchContract):
            metrics: list[str] = ["custom_metric"]

        mod.ExplicitContract = ExplicitContract
        sys.modules["_test_explicit"] = mod
        os.environ["CONTRACT_MODULE"] = "_test_explicit:ExplicitContract"

        try:
            contract = load_contract()
            self.assertIsInstance(contract, ExplicitContract)
            self.assertEqual(contract.metrics, ["custom_metric"])
        finally:
            del sys.modules["_test_explicit"]

    def test_caches_result(self):
        c1 = load_contract()
        c2 = load_contract()
        self.assertIs(c1, c2)

    def test_reset_cache_works(self):
        c1 = load_contract()
        reset_cache()
        c2 = load_contract()
        # Different instances after reset
        self.assertIsNot(c1, c2)


if __name__ == "__main__":
    unittest.main()
