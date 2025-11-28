# Core Concepts

This page explains the main concepts you must understand
before diving into individual workers.

---

## Public game repository and base class

To create a game, you must publish a **public GitHub repository** and package it on **PyPI**.

Inside this repo, you define a **base class** that all participant models must implement.

Example (simplified):

```python
class TrackerBase:
    def tick(self, data):
        """Receive latest market data."""
        raise NotImplementedError

    def predict(self, asset, horizon, step):
        """Return a distribution or prediction."""
        raise NotImplementedError
```

Participants:

- use the PyPI package to import the base class (preferably from a notebook quickstarter),
- implement their own model class by inheriting from `TrackerBase`,
- submit it on [https://hub.crunchdao.com/](https://hub.crunchdao.com/).

Because you control the base class:

- you control the methods that exist,
- you control the input format,
- you control the expected output format.

The orchestrator and ModelRunner library rely on this contract.

---

## Tick vs Predict

Two central ideas:

- **Tick**: send new information to models  
  Example: latest prices, features, state.

- **Predict**: ask models to make a prediction  
  Example: return a distribution over returns for the next 24 hours.

Typical flow:

1. Fetch or receive new market data.
2. Call `tick` on all models with that data.
3. Call `predict` on all models to get predictions.
4. Store predictions for scoring.

Tick may not return anything useful.
Predict must return a structured payload.

---

## Timeouts and failures

All calls to models are executed with a timeout. The ModelRunner library performs concurrent calls to all models and applies a timeout to ensure that a slow or unresponsive model cannot block the system.

A call is marked as:

- **timeout** if the model takes too long to respond.
- **failure** if the model raises an exception, or returns invalid data.

The ModelRunner keeps a counter of **consecutive failures** and **consecutive timeouts**.
When the limit is reached, the model is stopped and disconnected.

This protects your system from:

- buggy models,
- very slow models,
- models that do not respect the interface.

## Async and the event loop

The Predict worker is asynchronous for two reasons:

1. It must keep a **persistent connection** to the orchestrator.
2. It must be able to call many models concurrently.

The ModelRunner uses an event loop to:

- maintain a live list of models,
- detect when models join or leave,
- reconnect if needed.

Your own code must avoid blocking this event loop:

- do not run heavy computations directly in the Predict worker,
- delegate heavy work to the Score worker,
- keep network calls and DB writes efficient.

---

## Dynamic subclass vs factory

In the current implementation, the ModelRunner:

- scans the participant code,
- finds the first class that inherits from your base class,
- instantiates it automatically.

This is called a **dynamic subclass** approach.

In the future, we may switch to a **factory** approach, where each model:

- exposes a function like `create_model()`,
- returns the instance to run.

The goal is to:

- avoid ambiguity when there are many classes,
- make model construction more explicit.