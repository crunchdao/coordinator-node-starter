---
name: coordinator-node-starter
description: Use when setting up a new Crunch competition or customizing coordinator infrastructure. Guides through competition design decisions and implementation. ALWAYS run post-deployment verification after ANY code change.
---

# Coordinator Node Starter

Self-contained backend for running Crunch Competitions. The system receives predictions from participant models, scores them against ground truth, and exposes leaderboards via API. **No downstream services required** - this is the complete competition infrastructure.

## Architecture

```
     Data Source (API/Files/DB)          Model Orchestrator (gRPC)
              ↓                                    ↓
        ┌─────────────────────────────────────────────────────┐
        │                  Predict Worker                     │
        │    fetch data → tick(data) → predict() → store      │
        └─────────────────────────┬───────────────────────────┘
                                  ↓
        ┌─────────────────────────────────────────────────────┐
        │                   Score Worker                      │
        │    load predictions → compare to ground truth       │
        │         → compute scores → update leaderboard       │
        └─────────────────────────┬───────────────────────────┘
                                  ↓
        ┌─────────────────────────────────────────────────────┐
        │                Report Worker (FastAPI)              │
        │       /reports/leaderboard, /models, /scores        │
        └─────────────────────────────────────────────────────┘
```

---

## Competition Design Checklist

**When the user proposes a competition goal or target, work out a proposal for each of these decisions and present it for their validation:**

### 1. Data Source

**Ask the user:**
> "Where does your input data come from? Options include:
> - **REST API** (e.g., price feeds, weather data, sports stats)
> - **WebSocket** (real-time streaming)
> - **Database** (historical data, batch updates)
> - **Files** (CSV, Parquet uploaded periodically)
> - **Custom** (describe your data source)"

**Current implementation:** `condorgame_backend/infrastructure/http/` - fetches from REST APIs

**Propose:** Based on their answer, suggest adapting the data fetcher or creating a new one.

---

### 2. Input Data Shape

**Ask the user:**
> "What is the structure of your raw input data?
> - What fields/columns does it have?
> - What is the frequency (per-second, per-minute, daily)?
> - Is it time-series, tabular, images, text?
> - Example: `{timestamp, asset, price, volume}` or `{date, features[], target}`"

**Propose:** Suggest a data model that captures their domain:
```python
@dataclass
class InputData:
    timestamp: datetime
    # ... fields based on their answer
```

---

### 3. Data Pushed to Models

**Ask the user:**
> "What data should participant models receive? This may differ from raw input:
> - **Same as input** - pass through directly
> - **Transformed** - normalized, windowed, aggregated
> - **Subset** - only certain fields (hide target/future data)
> - **Enriched** - add computed features"

**Current implementation:** `predict_service.py` calls `tick(data)` with processed data

**Propose:** Based on their answer, define the `tick()` payload structure.

---

### 4. Model Interface

**Ask the user:**
> "What should participant models do?
> - **Input:** What does `tick(data)` receive?
> - **Output:** What does `predict()` return?
> - **State:** Can models maintain internal state between ticks?
> - **Constraints:** Time limits? Memory limits? Allowed libraries?"

**Propose:** A base class definition:
```python
class CompetitionModel(ABC):
    @abstractmethod
    def tick(self, data: YourDataType) -> None:
        """Receive new data. Update internal state."""
        pass
    
    @abstractmethod  
    def predict(self, **params) -> YourPredictionType:
        """Return prediction based on current state."""
        pass
```

---

### 5. Scoring Function

**Ask the user:**
> "How should predictions be scored?
> - **Metric:** MSE, MAE, accuracy, log-loss, custom?
> - **Timing:** When is ground truth available? (immediately, after delay, end of period)
> - **Aggregation:** Per-prediction, rolling window, cumulative?
> - **Penalties:** Late submissions, invalid formats?"

**Current implementation:** `condorgame_backend/services/score_service.py`

**Propose:** A scoring approach:
```python
def score_prediction(prediction: Prediction, ground_truth: GroundTruth) -> float:
    # Based on their metric choice
    return metric(prediction.value, ground_truth.value)
```

---

### 6. Leaderboard Design

**Ask the user:**
> "How should the leaderboard work?
> - **Ranking:** By total score, recent performance, weighted combination?
> - **Display:** What info to show? (rank, score, model name, trend)
> - **Updates:** Real-time, hourly, daily?
> - **Tiebreakers:** Earlier submission wins? Secondary metric?"

**Current implementation:** `condorgame_backend/entities/leaderboard.py`

**Propose:** Leaderboard structure:
```python
@dataclass
class LeaderboardEntry:
    rank: int
    model_id: str
    model_name: str
    score: float  # or composite score object
    # Additional fields based on their needs
```

---

### Implementation Workflow

After gathering requirements:

1. **Create data models** → `condorgame_backend/entities/`
2. **Implement data fetcher** → `condorgame_backend/infrastructure/http/`
3. **Define model interface** → `game_package/` (local) or publish to PyPI
4. **Implement scoring** → `condorgame_backend/services/score_service.py`
5. **Configure leaderboard** → `condorgame_backend/entities/leaderboard.py`
6. **Test end-to-end** → `make deploy && make logs`

---

## Defining Your Game's Base Class

Participants inherit from a base class you define. Start locally, publish to PyPI when ready.

### Step 1: Create Local Package (Prototyping)

Create the base class in this repo first:

```
game_package/
  __init__.py
  tracker.py
```

```python
# game_package/tracker.py
from abc import ABC, abstractmethod

class TrackerBase(ABC):
    """Base class that all participant models must inherit from."""
    
    @abstractmethod
    def tick(self, data: dict) -> None:
        """
        Receive latest market data.
        Called every time new data is available.
        
        Args:
            data: Dict of asset -> list of (timestamp, price) tuples
        """
        pass
    
    @abstractmethod
    def predict(self, asset: str, horizon: int, step: int) -> list:
        """
        Return predictions for the given asset.
        
        Args:
            asset: Asset code (e.g., "BTC")
            horizon: Total prediction window in seconds
            step: Interval between predictions in seconds
        
        Returns:
            List of predictions, one per step (length = horizon / step)
        """
        pass
```

```python
# game_package/__init__.py
from .tracker import TrackerBase

__all__ = ["TrackerBase"]
```

### Step 2: Configure Model Runner

Update `predict_service.py` to use your local base class:

```python
self.model_concurrent_runner = DynamicSubclassModelConcurrentRunner(
    # ...
    base_classname="game_package.tracker.TrackerBase",  # Your local package
    # ...
)
```

### Step 3: Test Locally

```bash
make deploy
# Create a test model in deployment/model-orchestrator-local/data/submissions/
# Check logs to verify tick/predict calls work
make logs SERVICES=model-orchestrator
```

### Step 4: Publish to PyPI (When Ready)

Once your prototype works, publish so participants can install it.

#### 4a. Create PyPI Account

1. Go to https://pypi.org/account/register/
2. Verify your email
3. Enable 2FA (required for publishing)
4. Create an API token: Account Settings → API tokens → Add API token
   - Scope: "Entire account" (first time) or specific project
   - **Save the token** - you won't see it again

#### 4b. Prepare Package for Publishing

Create a **new public GitHub repo** for your package (separate from this coordinator repo):

```
my-game-package/
  my_game/
    __init__.py
    tracker.py
  pyproject.toml
  README.md
  LICENSE
```

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-game-package"
version = "0.1.0"
description = "Base class for My Game competition"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
    {name = "Your Name", email = "you@example.com"}
]
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
]

[project.urls]
Homepage = "https://github.com/yourorg/my-game-package"
```

#### 4c. Build and Upload

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# Upload to PyPI (will prompt for token)
python -m twine upload dist/*
# Username: __token__
# Password: <paste your API token>
```

#### 4d. Update Coordinator to Use Published Package

Once published, update `predict_service.py`:

```python
self.model_concurrent_runner = DynamicSubclassModelConcurrentRunner(
    # ...
    base_classname="my_game.tracker.TrackerBase",  # Published package name
    # ...
)
```

Add to your `requirements.txt` or `pyproject.toml`:
```
my-game-package>=0.1.0
```

### PyPI Tips

| Task | Command |
|------|---------|
| Test upload first | Use TestPyPI: `twine upload --repository testpypi dist/*` |
| Install from TestPyPI | `pip install --index-url https://test.pypi.org/simple/ my-game-package` |
| Update version | Change version in `pyproject.toml`, rebuild, re-upload |
| Check package | `pip install my-game-package && python -c "from my_game import TrackerBase"` |

## Quick Commands

| Command | Purpose |
|---------|---------|
| `make deploy` | Start full stack |
| `make deploy dev` | Start infra only (run workers from IDE) |
| `make logs` | All service logs |
| `make logs SERVICES=predict-worker` | Specific service logs |
| `make restart` | Restart all |
| `make down` | Stop and remove |
| `docker compose ps` | Check service status |

## Post-Deployment Verification (REQUIRED)

**After ANY code change or deployment, ALWAYS run these checks:**

```bash
# 1. Wait for services to stabilize (5-10 seconds)
sleep 5

# 2. Check for errors in ALL workers
make logs SERVICES="score-worker predict-worker report-worker" 2>&1 | grep -i "error\|exception\|traceback\|failed\|validation" | tail -20

# 3. Verify services are running (no restarts)
docker compose ps

# 4. Quick health check - look for normal operation logs
make logs SERVICES=score-worker 2>&1 | tail -10
```

**If ANY errors appear, investigate and fix before considering deployment complete.**

### Error Patterns to Watch For

| Error Pattern | Likely Cause |
|---------------|--------------|
| `ValidationError` / `pydantic` | Data model mismatch (None where value expected, wrong type) |
| `Connection refused` | Wrong host config (localhost vs service name in Docker) |
| `KeyError` / `AttributeError` | Missing data, None checks needed |
| `TimeoutError` | External service slow/down |

## Debugging Playbook

### Step 1: Check Services Running

```bash
docker compose ps
```

Look for:
- **Exit codes** - non-zero means crash
- **Restart count** - high count means crash loop
- **Status** - should be "running" or "healthy"

### Step 2: Identify Failing Layer

| Symptom | Check This | Command |
|---------|------------|---------|
| Models not connecting | model-orchestrator | `make logs SERVICES=model-orchestrator` |
| Models not receiving ticks | model-orchestrator | `make logs SERVICES=model-orchestrator` |
| Model errors/exceptions | model-orchestrator | `make logs SERVICES=model-orchestrator` |
| Predictions not stored | predict-worker | `make logs SERVICES=predict-worker` |
| Scores not appearing | score-worker | `make logs SERVICES=score-worker` |
| API returning errors | report-worker | `make logs SERVICES=report-worker` |
| DB connection issues | postgres | `make logs SERVICES=postgres` |

### Step 3: Common Failure Patterns

#### "Models not receiving ticks"

**Check model-orchestrator logs:**
```bash
make logs SERVICES=model-orchestrator
```

**Look for:**
- `Connection refused` - orchestrator not ready, model crashed
- `Model not found` - check `models.dev.yml` configuration
- Model not in `RUNNING` state - check `desired_state` in config

**Verify model config:**
```
deployment/model-orchestrator-local/config/models.dev.yml
```

#### "Model returns no values / timeout"

**Check model-orchestrator logs for Python exceptions:**
```bash
make logs SERVICES=model-orchestrator 2>&1 | grep -A 10 "Exception\|Error\|Traceback"
```

**Look for:**
- Import errors in model code
- Runtime exceptions during `tick()` or `predict()`
- Model marked as failed after consecutive failures (default: 100)

**In predict-worker logs:**
```bash
make logs SERVICES=predict-worker
```

Look for: `Tick finished with X success, Y failed and Z timed out`

#### "Predictions not being stored"

**Check predict-worker logs:**
```bash
make logs SERVICES=predict-worker
```

**Look for:**
- DB connection errors
- `predictions got` count - should match model count
- `missing predictions (models sit out)` - models that didn't respond

#### "Scores not appearing"

**This is often NORMAL!** Prediction horizon is typically 1 hour, so scores take 1+ hour to appear.

**If waited long enough, check score-worker:**
```bash
make logs SERVICES=score-worker
```

**Look for:**
- `No predictions to score` - predictions not yet resolvable
- `Scored X predictions, Y failed` - scoring errors
- `No price data found` - price feed issues
- `Minimum score: X` - very negative = potential issues

#### "API not returning data"

**Check report-worker logs:**
```bash
make logs SERVICES=report-worker
```

**Test endpoints directly:**
```bash
curl http://localhost:8000/reports/leaderboard
curl http://localhost:8000/reports/models
```

### Step 4: Database Inspection

**Connect to postgres:**
```bash
docker compose exec postgres psql -U condorgame -d condorgame
```

**Useful queries:**
```sql
-- Check prediction counts
SELECT model_id, COUNT(*) FROM predictions GROUP BY model_id;

-- Check recent predictions
SELECT id, model_id, status, performed_at FROM predictions ORDER BY performed_at DESC LIMIT 10;

-- Check scored predictions
SELECT id, model_id, score_value, score_success FROM predictions WHERE score_scored_at IS NOT NULL ORDER BY score_scored_at DESC LIMIT 10;

-- Check leaderboard
SELECT * FROM leaderboards ORDER BY created_at DESC LIMIT 1;
```

### Step 5: Full Pipeline Trace

To trace a prediction through the entire pipeline:

```bash
# 1. Watch predict-worker create prediction
make logs SERVICES=predict-worker 2>&1 | grep -i "predict\|tick"

# 2. Watch score-worker score it (after horizon passes)
make logs SERVICES=score-worker 2>&1 | grep -i "score\|leaderboard"

# 3. Verify in API
curl http://localhost:8000/reports/leaderboard | jq
```

## Customization Sub-Skills

When you need to customize specific components, read the relevant sub-skill:

| What to Customize | Sub-Skill Location |
|-------------------|-------------------|
| Data sources (prices, features) | `condorgame_backend/infrastructure/http/SKILL.md` |
| Scoring algorithm | `condorgame_backend/services/SKILL.md` |
| Prediction format | `condorgame_backend/entities/SKILL.md` |
| Leaderboard & reports | `condorgame_backend/workers/SKILL.md` |

## Key Files Reference

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Service definitions |
| `docker-compose-local.yml` | Local dev overrides |
| `.local.env` / `.dev.env` | Environment config |
| `deployment/model-orchestrator-local/config/` | Model orchestrator config |
| `condorgame_backend/workers/` | Worker entry points |
| `condorgame_backend/services/` | Business logic |
| `condorgame_backend/entities/` | Domain models |
| `condorgame_backend/infrastructure/` | DB, HTTP, caching |

## Prerequisites & Installation

### Required: Docker

Docker runs all services (workers, database, orchestrator). Install Docker Desktop:

| OS | Installation |
|----|--------------|
| **macOS** | `brew install --cask docker` or [Docker Desktop](https://docs.docker.com/desktop/install/mac-install/) |
| **Windows** | [Docker Desktop](https://docs.docker.com/desktop/install/windows-install/) (requires WSL2) |
| **Linux** | `curl -fsSL https://get.docker.com | sh` or [Docker Engine](https://docs.docker.com/engine/install/) |

**Verify installation:**
```bash
docker --version
docker compose version
```

**Start Docker** (if not running):
- macOS/Windows: Open Docker Desktop app
- Linux: `sudo systemctl start docker`

### Required: Make

Most systems have `make` pre-installed. If not:

| OS | Installation |
|----|--------------|
| **macOS** | `xcode-select --install` |
| **Windows** | Install via [chocolatey](https://chocolatey.org/): `choco install make` |
| **Ubuntu/Debian** | `sudo apt install build-essential` |

### Optional: Python (for local development)

Only needed if running workers outside Docker (`make deploy dev`):

```bash
# Check Python version (3.11+ recommended)
python --version

# Install dependencies
pip install -r requirements.txt
```

### Optional: jq (for JSON formatting)

Useful for inspecting API responses:

| OS | Installation |
|----|--------------|
| **macOS** | `brew install jq` |
| **Ubuntu/Debian** | `sudo apt install jq` |
| **Windows** | `choco install jq` |

### Quick Start After Installation

```bash
# 1. Clone the repo
git clone https://github.com/crunchdao/coordinator-node-starter
cd coordinator-node-starter

# 2. Start everything
make deploy

# 3. Verify services are running
docker compose ps

# 4. Check the UIs
# Reports/Leaderboard: http://localhost:3000
# Documentation:       http://localhost:8080
# API:                 http://localhost:8000/docs
```

### Troubleshooting Installation

| Problem | Solution |
|---------|----------|
| `docker: command not found` | Install Docker, ensure it's in PATH |
| `Cannot connect to Docker daemon` | Start Docker Desktop or `sudo systemctl start docker` |
| `make: command not found` | Install make (see above) |
| `port already in use` | Stop conflicting service or change ports in `.local.env` |
| Permission denied on Linux | Add user to docker group: `sudo usermod -aG docker $USER` (then logout/login) |
