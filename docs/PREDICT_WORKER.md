# Predict Worker

Canonical entrypoint:
- `node_template/workers/predict_worker.py`

Main service:
- `node_template/services/predict_service.py`

Responsibilities:
- load active prediction configs
- fetch raw input via `RAW_INPUT_PROVIDER`
- build inference input via configured callable
- call model runner (`tick` / `predict`)
- validate output
- persist predictions and model metadata
