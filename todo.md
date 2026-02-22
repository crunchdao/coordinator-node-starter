### What Can We Learn to Improve the Build Flow?

 1. The starter template carries too much dead weight that every competition copies.

 V3's crunch_config.py is a character-for-character copy of the template. V4's is a 377-line file where ~150 lines are identical boilerplate (Meta, RawInput, AggregationWindow, build_emission, frac64). The template should provide a base
 class that competitions extend, not a monolith to copy-paste:

 ```python
   # What it should look like
   from coordinator_node.config import BaseCrunchConfig, PredictionScope, Aggregation

   class CrunchConfig(BaseCrunchConfig):
       output_type = InferenceOutput  # only override what's different
       scope = PredictionScope(subject="BTCUSDT", horizon_seconds=120)
       aggregation = Aggregation(ranking_key="avg_pnl")
       resolve_ground_truth = my_resolver
       aggregate_snapshot = vanta_aggregate_snapshot
 ```

 2. The scoring function is the single most important file — it should be generated first, not left as a stub.

 V3's scoring is a 10-line stub that returns 0.0. It was never filled in during the build. This means the entire pipeline "works" but produces meaningless results. The scoring function should be the first thing generated from domain
 requirements, ideally with unit tests.

 3. resolve_ground_truth is the second most important function and the hardest to get right.

 V4 discovered that 60s windows with 1m candles produce 0.0 returns — after deploying. This should have been caught by a ground truth sanity check: "does the resolver actually produce non-zero returns with the configured feed
 granularity?"

 4. Multi-asset is a common pattern but the framework doesn't support it natively.

 V4's resolver hacks around single-subject ground truth by querying the DB directly. This is a pattern that should be a first-class feature: FEED_SUBJECTS=BTCUSDT,ETHUSDT → ground truth automatically resolves for all subjects.

 5. ~~The InferenceOutput type matters more than you'd think.~~ ✅ DONE

 ~~V3 uses {"value": float} (from the starter template) but the model examples return {"score": 0.5} — a key mismatch that would silently produce wrong results. V4 uses {"orders": dict} which is harder to mess up.~~
 Fixed: ScoreService now coerces raw inference_output dicts through contract.output_type before passing to the scoring function (fills defaults, coerces types). Added validate_scoring_io() startup check that dry-runs the scoring function with default InferenceOutput/GroundTruth to catch KeyError mismatches at boot time.

 6. ~~make deploy should include make init-db automatically.~~ ✅ DONE

 ~~Both V3 and V4 hit the same issue: fresh postgres volume → tables don't exist → workers crash. The deploy target should handle this.~~
 Fixed: Removed `profiles: [init]` from init-db service, added `depends_on: init-db: condition: service_completed_successfully` to all workers, and updated Makefile deploy to explicitly run init-db before bringing up services.

 7. The backtest harness (V3) should be a standard feature, not competition-specific.

 V3's BacktestRunner is generic enough to work for any competition. It should be in the starter template or a shared library. V4 lacks it entirely, which means there's no way to validate scoring logic offline.

 8. Docker networking internal: true breaks feed workers that need internet.

 Both V3 and V4 would hit this if using Binance. V3 avoided it by using Pyth (which apparently doesn't need external access in the same way). The template should document this or provide the 3-network pattern by default.

 9. The predict method signature should be enforced by the framework.

 V3's predict(**kwargs) allows anything. V4's predict(subject, horizon_seconds, step_seconds) is better but still not validated. The CallMethodConfig in V4's crunch_config.py is the right idea but disconnected from the actual tracker
 base class.

 ### Concrete Improvements for the Starter Template

 ┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────┐
 │ Change                                                                                                              │ Impact                                                                  │
 ├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
 │ Extract BaseCrunchConfig into coordinator-node so competitions only override what's different                       │ Eliminates 150+ lines of boilerplate per competition                    │
 ├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
 │ ~~Add make init-db to make deploy recipe~~  ✅ DONE                                                                  │ Prevents "tables don't exist" crash on fresh deploy                     │
 ├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
 │ Add a make smoke-test that checks: API healthy, predictions flowing, scores non-zero, ground truth returns non-zero │ Catches the 0.0-scoring and 0.0-ground-truth bugs immediately           │
 ├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
 │ Default 3-network Docker topology (frontend/backend/external)                                                       │ Prevents the Binance DNS issue                                          │
 ├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
 │ Add backtest.py to the starter challenge template                                                                   │ Every competition gets offline eval                                     │
 ├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
 │ Add a SKILL.md generator to the build flow                                                                          │ V3 had them, V4 didn't — they're valuable for re-entering the workspace │
 ├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
 │ Default non-root Docker user + healthchecks + resource limits                                                       │ V4 did this manually, should be default                                 │
 ├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
 │ Add resolve_after_seconds validation: warn if < 2× feed granularity                                                 │ Prevents the 0.0 returns bug                                            │
 ├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
 │ Document multi-asset pattern (custom ground truth resolver) as a standard extension                                 │ V4's pattern is reusable                                                │
 └─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────┘