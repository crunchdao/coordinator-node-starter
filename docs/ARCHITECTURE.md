# Architecture & Design Principles

## Overview

The coordinator-node-starter is a template system for building competition coordinators ("Crunches"). Each coordinator runs a predict → score → rank loop against participant models, fed by live market data.

The architecture is built on five core principles:

1. Canonical schema with JSONB extension
2. Deterministic callable wiring via packs
3. Generated skill files that guide LLM agents
4. Shared runtime library (`coordinator_runtime`)
5. Two-repo separation per competition

---

## 1. Canonical Schema + JSONB Extension

Every coordinator shares the same Postgres table structure. Protocol-required columns are typed and indexed. Competition-specific data lives in JSONB columns.

```mermaid
erDiagram
    MODELS {
        string id PK
        string name
        string player_id
        jsonb overall_score_jsonb "← competition-specific"
        jsonb scores_by_scope_jsonb "← competition-specific"
        jsonb meta_jsonb "← competition-specific"
    }
    PREDICTIONS {
        string id PK
        string model_id FK
        string scope_key
        jsonb scope_jsonb "← competition-specific"
        jsonb inference_input_jsonb "← competition-specific"
        jsonb inference_output_jsonb "← competition-specific"
        float score_value
        bool score_success
    }
    MODEL_SCORES {
        string id PK
        string model_id FK
        jsonb score_payload_jsonb "← competition-specific"
    }
    LEADERBOARDS {
        string id PK
        jsonb entries_jsonb "← competition-specific"
        jsonb meta_jsonb "← competition-specific"
    }

    MODELS ||--o{ PREDICTIONS : "model_id"
    MODELS ||--o{ MODEL_SCORES : "model_id"
```

The key insight: **typed columns for protocol queries, JSONB columns for competition-specific payloads**.

```
┌──────────────────────────────────────────────────────────────────┐
│                     Same canonical tables                        │
│                                                                  │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐           │
│  │ BTC Price   │   │ NLP         │   │ Portfolio    │           │
│  │ Predictor   │   │ Sentiment   │   │ Optimizer    │           │
│  │             │   │             │   │              │           │
│  │ scope_jsonb:│   │ scope_jsonb:│   │ scope_jsonb: │           │
│  │ {asset,     │   │ {corpus,    │   │ {universe,   │           │
│  │  horizon}   │   │  window}    │   │  rebalance}  │           │
│  └─────────────┘   └─────────────┘   └─────────────┘           │
│                                                                  │
│  Zero schema migrations. Same queries. Different payloads.       │
└──────────────────────────────────────────────────────────────────┘
```

Separately, `market_records` is a **high-volume append table** for raw market data. Each data point is its own row with typed/indexed columns for querying (`provider`, `asset`, `kind`, `granularity`, `ts_event`). JSONB is only used for the per-record value shape, which varies by data kind:

```mermaid
erDiagram
    MARKET_RECORDS {
        string id PK
        string provider "indexed"
        string asset "indexed"
        string kind "indexed (tick or candle)"
        string granularity "indexed"
        datetime ts_event "indexed"
        datetime ts_ingested "indexed"
        jsonb values_jsonb "← varies by kind"
        jsonb meta_jsonb
    }
    MARKET_INGESTION_STATE {
        string id PK
        string provider "indexed"
        string asset "indexed"
        string kind "indexed"
        string granularity "indexed"
        datetime last_event_ts "watermark"
    }

    MARKET_RECORDS }o--|| MARKET_INGESTION_STATE : "scope"
```

```
 tick row:   values_jsonb = {"price": 44987.5}
 candle row: values_jsonb = {"open": 45000, "high": 45010, "low": 44980, "close": 44992, "volume": 12.3}
```

This is not a JSONB-array-per-feed design. One row per data point, uniquely indexed on `(provider, asset, kind, granularity, ts_event)` for dedup and fast time-range queries.

This means:

- **New competitions don't require schema migrations.** A BTC price predictor and an NLP sentiment ranker use the same tables — they just put different shapes inside the JSONB columns.
- **Core queries work everywhere.** Filtering predictions by model, time range, or scope works identically regardless of what's inside the payloads.
- **The webapp, CLI tools, and report APIs work against known column names** while competition-specific UI (column labels, metric widgets) reads from configurable schema endpoints.

The canonical tables are defined once in `coordinator_core/infrastructure/db/db_tables.py` and shared across all generated workspaces via vendoring.

---

## 2. Deterministic Callable Wiring via Packs

A coordinator's behavior is defined by **ten callable slots** that form the full predict → score → rank pipeline:

```mermaid
flowchart LR
    subgraph "Data Ingestion"
        RAW[RAW_INPUT_PROVIDER]
    end

    subgraph "Prediction Pipeline"
        INP[INFERENCE_INPUT_BUILDER]
        SCOPE[PREDICTION_SCOPE_BUILDER]
        CALL[PREDICT_CALL_BUILDER]
        VAL[INFERENCE_OUTPUT_VALIDATOR]
    end

    subgraph "Scoring Pipeline"
        GT[GROUND_TRUTH_RESOLVER]
        SCORE[SCORING_FUNCTION]
        AGG[MODEL_SCORE_AGGREGATOR]
        RANK[LEADERBOARD_RANKER]
    end

    subgraph "Reporting"
        SCHEMA[REPORT_SCHEMA_PROVIDER]
    end

    RAW --> INP --> SCOPE --> CALL --> VAL
    VAL --> GT --> SCORE --> AGG --> RANK
    RANK --> SCHEMA
```

| Slot | Responsibility |
|------|---------------|
| `RAW_INPUT_PROVIDER` | Fetch/build the raw data payload for a prediction cycle |
| `INFERENCE_INPUT_BUILDER` | Transform raw input into what models receive |
| `INFERENCE_OUTPUT_VALIDATOR` | Validate model responses |
| `SCORING_FUNCTION` | Score a single prediction against ground truth |
| `GROUND_TRUTH_RESOLVER` | Resolve what actually happened (from market tape or external source) |
| `MODEL_SCORE_AGGREGATOR` | Aggregate per-prediction scores into per-model scores |
| `LEADERBOARD_RANKER` | Rank models into a leaderboard snapshot |
| `REPORT_SCHEMA_PROVIDER` | Define the leaderboard column / metrics widget schema for the UI |
| `PREDICTION_SCOPE_BUILDER` | Build the scope dimensions for each prediction |
| `PREDICT_CALL_BUILDER` | Assemble the final model invocation payload |

**Packs** are JSON manifests that pre-wire all ten slots:

```mermaid
flowchart TD
    CLI["coordinator init btc-trader --pack realtime"]
    CLI --> PackJSON["packs/realtime/pack.json"]

    PackJSON --> |"reads"| Callables["10 callable paths"]
    PackJSON --> |"reads"| Schedule["scheduled_prediction_configs"]
    PackJSON --> |"reads"| Interval["checkpoint_interval_seconds"]

    Callables --> Env["config/callables.env"]
    Schedule --> JSON["config/scheduled_prediction_configs.json"]
    Interval --> DotEnv[".local.env"]

    subgraph "Override any slot"
        Spec["--spec spec.json"] -.-> |"merges over"| Callables
        Manual["edit callables.env"] -.-> |"replaces"| Env
    end
```

Available packs:

- **baseline** — 60s cycles, balanced local development
- **realtime** — 15s cycles, low-latency tournament
- **tournament** — combined in-sample + out-of-sample scopes

Callable paths use Python dotted-module notation (`runtime_definitions.data:provide_raw_input`). Workers load them at startup via `importlib`, so no code changes are needed to swap behavior — just change the env var.

---

## 3. Generated Skill Files (LLM Agent Guidance)

Every scaffolded workspace includes three `SKILL.md` files — structured instructions for coding agents:

```mermaid
flowchart TD
    Init["coordinator init btc-trader"] --> WS["btc-trader/"]

    WS --> WSSkill["SKILL.md\n(workspace)"]
    WS --> Node["crunch-node-btc-trader/"]
    WS --> Challenge["crunch-btc-trader/"]

    Node --> NodeSkill["SKILL.md\n(node)"]
    Challenge --> ChalSkill["SKILL.md\n(challenge)"]

    WSSkill --> |"tells agent"| A1["make deploy\nmake verify-e2e\nwhere logs live"]
    NodeSkill --> |"tells agent"| A2["health endpoints\nedit boundaries\nruntime_definitions/"]
    ChalSkill --> |"tells agent"| A3["tracker.py\nscoring.py\nexamples/\nwhere node callables live"]

    style WSSkill fill:#2d5016,color:#fff
    style NodeSkill fill:#2d5016,color:#fff
    style ChalSkill fill:#2d5016,color:#fff
```

The idea: `coordinator init` produces the hard 80% (working infrastructure, wired callables, running stack). The SKILL files prompt an LLM to fill in the remaining 20% — the actual competition logic — by pointing it at the right files and explaining the constraints.

---

## 4. Shared Runtime Library (`coordinator_runtime`)

Code that is **common across all coordinators** lives in `coordinator_runtime/`:

```mermaid
flowchart TD
    subgraph coordinator_runtime
        direction TB
        Contracts["contracts.py\nMarketRecord, AssetDescriptor\nFeedSubscription, FeedFetchRequest"]
        Base["base.py\nDataFeed protocol\nFeedSink, FeedHandle"]
        Registry["registry.py\nDataFeedRegistry\ncreate_from_env()"]
        Defaults["defaults.py\n10 default callable\nimplementations"]

        subgraph providers
            Pyth["pyth.py\nPythFeed"]
            Binance["binance.py\nBinanceFeed"]
        end

        subgraph storage
            Parquet["parquet stub\n(future cold storage)"]
        end
    end

    subgraph node_template
        MDW["market_data_worker"]
        PW["predict_worker"]
        SW["score_worker"]
        RW["report_worker"]
        DBRepo["DBMarketRecordRepository"]
    end

    Registry --> Pyth
    Registry --> Binance
    MDW --> Registry
    MDW --> DBRepo
    PW --> Defaults
    SW --> Defaults
    RW --> DBRepo
    DBRepo --> Parquet

    style coordinator_runtime fill:#1a365d,color:#fff
    style node_template fill:#553c16,color:#fff
```

### Feed Architecture

Provider adapters implement a dual-mode protocol:

```mermaid
sequenceDiagram
    participant W as market_data_worker
    participant R as DataFeedRegistry
    participant F as Feed Adapter (Pyth/Binance)
    participant DB as market_records table

    Note over W: Startup
    W->>R: create_from_env(FEED_PROVIDER=pyth)
    R->>F: build_pyth_feed(settings)
    R-->>W: feed instance

    Note over W: Backfill (pull mode)
    W->>F: fetch(FeedFetchRequest)
    F-->>W: Sequence[MarketRecord]
    W->>DB: upsert records

    Note over W: Live ingestion (push mode)
    W->>F: listen(FeedSubscription, sink)
    loop every poll interval
        F->>F: fetch latest
        F-->>W: sink.on_record(MarketRecord)
        W->>DB: upsert record
    end

    Note over W: Ground truth resolution
    W->>DB: query by (asset, ts_event range)
    DB-->>W: stored records (tape-first)
    alt records missing
        W->>F: fetch(recovery window)
        F-->>W: backfill records
    end
```

Provider adapters prefer SDK packages (e.g. `python-binance`) for external connections, with HTTP fallback if the package is unavailable.

### Tape-First Pattern

```
┌─────────────────────────────────────────────────────┐
│                  Ground Truth Resolution             │
│                                                      │
│   1. Query market_records for (asset, time window)   │
│              │                                       │
│              ▼                                       │
│        Records found? ──yes──► Use stored values     │
│              │                                       │
│              no                                      │
│              │                                       │
│              ▼                                       │
│   2. Fetch from live feed (recovery)                 │
│              │                                       │
│              ▼                                       │
│   3. Store fetched records for future queries        │
│              │                                       │
│              ▼                                       │
│        Return resolved ground truth                  │
│                                                      │
│   TTL retention based on market time (ts_event)      │
│   not ingest time                                    │
└─────────────────────────────────────────────────────┘
```

---

## 5. Two-Repo Separation

Each competition produces two repositories with a clear visibility boundary:

```mermaid
flowchart LR
    subgraph "Public (participants see this)"
        Challenge["crunch-btc-trader/"]
        Tracker["tracker.py\nmodel interface"]
        Scoring["scoring.py\nlocal self-eval"]
        Examples["examples/\nquickstarters"]
        Schemas["schemas/\npayload docs"]
    end

    subgraph "Private (operator only)"
        Node["crunch-node-btc-trader/"]
        Compose["docker-compose.yml"]
        RuntimeDefs["runtime_definitions/\ndata, inference,\nvalidation, reporting"]
        Config["config/\ncallables.env\nschedule.json"]
        Vendored["runtime/\ncoordinator_core\ncoordinator_runtime\nnode_template"]
    end

    Challenge --> Tracker
    Challenge --> Scoring
    Challenge --> Examples
    Challenge --> Schemas

    Node --> Compose
    Node --> RuntimeDefs
    Node --> Config
    Node --> Vendored

    Node -. "mounts at /app/challenge" .-> Challenge

    style Challenge fill:#2d5016,color:#fff
    style Node fill:#7c2d12,color:#fff
```

| Repo | Visibility | Contains |
|------|-----------|----------|
| `crunch-<name>` | **Public** | Model interface (`tracker.py`), scoring logic, quickstarter examples, schemas |
| `crunch-node-<name>` | **Private** | Deployment config, callable wiring, runtime definitions, vendored runtime packages |

This separation means participants see only the challenge contract — not the infrastructure, scoring weights, or data pipeline internals.

The node workspace is self-contained: it vendors `coordinator_core`, `coordinator_runtime`, and `node_template` into a `runtime/` directory and builds a single Docker image from them. No dependency on the template repo at runtime.

---

## How It Fits Together

### Scaffold Output

```
coordinator init btc-trader --pack realtime
│
├─ reads pack JSON (callables, schedule, checkpoint interval)
├─ renders templates (Dockerfile, docker-compose, Makefile, SKILL files)
├─ generates .local.env + config/callables.env with all 10 slots wired
├─ vendors coordinator_core + coordinator_runtime + node_template
│
└─ btc-trader/
   ├─ SKILL.md                       ← workspace agent guidance
   ├─ process-log.jsonl              ← scaffold audit trail
   │
   ├─ crunch-btc-trader/             ← public challenge package
   │  ├─ SKILL.md                    ← challenge agent guidance
   │  ├─ crunch_btc_trader/
   │  │  ├─ tracker.py               ← model interface (fill this in)
   │  │  ├─ scoring.py               ← scoring function (fill this in)
   │  │  └─ examples/                ← quickstarters for participants
   │  └─ pyproject.toml
   │
   └─ crunch-node-btc-trader/        ← private node runtime
      ├─ SKILL.md                    ← node agent guidance
      ├─ RUNBOOK.md                  ← troubleshooting guide
      ├─ docker-compose.yml          ← all services pre-wired
      ├─ Dockerfile
      ├─ Makefile                    ← deploy/verify/logs targets
      ├─ .local.env                  ← environment config
      ├─ runtime_definitions/        ← node-private callables
      │  ├─ data.py                  ← tape-first input + ground truth
      │  ├─ inference.py             ← input builder
      │  ├─ validation.py            ← output validator
      │  └─ reporting.py             ← UI schema
      ├─ config/
      │  ├─ callables.env            ← all 10 callable paths
      │  └─ scheduled_prediction_configs.json
      └─ runtime/                    ← vendored packages
         ├─ coordinator_core/
         ├─ coordinator_runtime/
         └─ node_template/
```

### Running Stack

```mermaid
flowchart TB
    subgraph Docker Compose
        PG[(Postgres\ncanonical schema)]

        MDW[market-data-worker\nfeed → market_records]
        PW[predict-worker\ncalls models]
        SW[score-worker\nscores + leaderboard]
        RW[report-worker\nread API]
        MO[model-orchestrator\nmanages model containers]
        UI[report-ui\nNext.js webapp]
    end

    PG --- MDW
    PG --- PW
    PG --- SW
    PG --- RW

    PW <--> MO
    MO <--> Models["Participant\nModel Containers"]

    UI --> |"/api/*"| RW

    subgraph "External Data"
        Pyth[Pyth Network]
        Binance[Binance API]
    end

    MDW --> Pyth
    MDW --> Binance

    subgraph "User Browser"
        Browser["localhost:3000\nLeaderboard · Metrics\nModels · Logs · Feeds"]
    end

    Browser --> UI

    style PG fill:#336791,color:#fff
    style UI fill:#1a365d,color:#fff
    style Models fill:#553c16,color:#fff
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSONB for all competition-specific data | No migrations per competition. Same queries, different payloads. |
| Ten callable slots, not plugin classes | Simple to reason about. One function per concern. Swappable via env. |
| Packs, not inheritance | Flat JSON config. No class hierarchies. Easy to diff and override. |
| Tape-first ground truth | Deterministic scoring from stored data. Feed failures don't block scoring. |
| Vendor at scaffold time | Node workspace works offline. No implicit dependency on template repo. |
| Generated SKILL files | Agents get structured guidance, not just code. The scaffold is documentation. |
| SDK-first for external APIs | Explicit, testable dependencies. HTTP fallback for resilience. |
| Feed visibility in UI is data-driven | Feeds nav appears only when feed data exists. Zero config for the operator. |
