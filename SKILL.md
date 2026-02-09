---
name: coordinator-node-starter
description: Use when working with Crunch competition infrastructure - debugging workers, customizing data sources, scoring, predictions, or leaderboards. Load this first, then sub-skills as needed.
---

# Coordinator Node Starter

Backend for Crunch Competitions, running on Coordinator Nodes. Predict/Score/Report workers receive predictions from participant models, score them, and expose leaderboards.

## Architecture

```
Price Sources (CrunchDAO/Pyth)     Model Orchestrator (gRPC)
              ↓                            ↓
        ┌─────────────────────────────────────────┐
        │           Predict Worker                │
        │  fetch prices → tick() → predict()     │
        │            → store predictions          │
        └─────────────────┬───────────────────────┘
                          ↓
        ┌─────────────────────────────────────────┐
        │            Score Worker                 │
        │  load predictions → score vs actual     │
        │     → rolling windows → leaderboard     │
        └─────────────────┬───────────────────────┘
                          ↓
        ┌─────────────────────────────────────────┐
        │           Report Worker (FastAPI)       │
        │  /reports/leaderboard, /models, etc.    │
        └─────────────────────────────────────────┘
```

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
