# Build Your Own Challenge

This page explains how to reuse this architecture
to create your own game.

---

## Step 1 – Create a public game repository

Create a public GitHub repository that will be the **official game repo**.

It should contain:

- the base class that models must implement,
- example models,
- documentation (quick start, interface description),
- information about:
  - input data,
  - expected outputs,
  - scoring rules.

---

## Step 2 – Define the base class

Decide what models must implement.

Example:

```python
class MyGameBaseModel:
    def on_tick(self, data):
        """Receive latest features."""
        raise NotImplementedError

    def predict(self, asset, horizon, step):
        """Return a JSON payload with a distribution."""
        raise NotImplementedError
```

Document:

- the format of `data`,
- the meaning of `asset`, `horizon`, `step`,
- the expected structure of the return value.

---

## Step 3 – Provide examples

Add at least one **benchmark model**:

- very simple,
- but fully working,
- good to copy-paste.

This model will also be useful for your own local tests.

---

## Step 4 – Connect to the orchestrator

In your Predict worker, configure the ModelRunner client
to talk to the orchestrator:

- in local mode through Docker,
- in production mode through a node managed by CrunchDAO.

Once `runner.init()` and `runner.sync()` are called,
you can start sending ticks and predicts.

---

## Step 5 – Implement scoring and reporting

Decide:

- how you want to score models,
- how often you want to update scores,
- which metrics you want to show in the leaderboard.

Implement the Score worker accordingly,
and expose results via the Report worker.

---

## Step 6 – Add your business logic

This example focuses only on:

- getting predictions,
- scoring them,
- displaying metrics.

In your real system, you might:

- send predictions to clients,
- use them in a trading engine,
- combine them into meta-models,
- feed them into another product.

You can plug this game architecture into your own core service.

---

## Step 7 – Iterate

As you get more participants and more feedback:

- adjust scoring,
- adjust timeouts and capacity,
- refine metrics and UI,
- simplify onboarding and documentation.

The architecture is flexible enough to grow with your game.
