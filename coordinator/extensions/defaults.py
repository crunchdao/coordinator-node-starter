from __future__ import annotations

"""
Legacy defaults module — kept for backward compatibility.

All Tier 2 callables (input building, output validation, aggregation,
ranking, report schema, scope building, predict call building) are now
handled by the CrunchContract. Only Tier 1 callables (scoring, raw input,
ground truth) remain as configurable extension points.
"""
