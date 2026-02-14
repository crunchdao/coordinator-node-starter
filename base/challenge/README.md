# challenge

Public challenge package.

Primary package: `starter_challenge`

## Participant-facing files

- `tracker.py` — model interface (participants subclass `TrackerBase`)
- `scoring.py` — scoring function for local self-eval
- `backtest.py` — backtest harness (`BacktestClient`, `BacktestRunner`, `BacktestResult`)
- `config.py` — baked-in coordinator URL and default feed dimensions
- `examples/` — quickstarter model implementations

## Backtest usage

```python
from starter_challenge.backtest import BacktestRunner
from my_model import MyTracker

result = BacktestRunner(model=MyTracker()).run(
    start="2026-01-01", end="2026-02-01"
)
result.predictions_df   # DataFrame in notebook
result.metrics           # rolling window aggregates matching production
result.summary()         # formatted output
```

Data is automatically fetched from the coordinator and cached locally.
No coordinator URL or feed configuration needed — baked into the package.

## Node-private runtime

- `../node/runtime_definitions/` — CrunchContract, runtime callables
