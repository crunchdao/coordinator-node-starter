# Introduction

## Purpose

This repository standardizes coordinator-node foundations so each new Crunch starts from the same protocol-safe base.

## Main packages

- `coordinator_core/`
  - canonical DB schema
  - stable entities
  - repository/service interfaces
- `node_template/`
  - default workers (`predict`, `score`, `report`)
  - extension loading via callable paths
  - DB repositories/session/init

## Extension model

Crunch-specific behavior is loaded via config:

- `INFERENCE_INPUT_BUILDER`
- `INFERENCE_OUTPUT_VALIDATOR`
- `SCORING_FUNCTION`
- `MODEL_SCORE_AGGREGATOR`
- `LEADERBOARD_RANKER`
- `CHECKPOINT_INTERVAL_SECONDS`

## Two-repo model

For each Crunch, create:

- `crunch-<name>` (public contracts, schemas, scoring)
- `crunch-node-<name>` (private runnable node based on template)
