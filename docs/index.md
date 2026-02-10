# Condor-style Game Documentation

Welcome to this documentation.

This site explains how to start your Coordinator Node on the Crunch protocol:

- You talk to **one model orchestrator**.
- The orchestrator runs **many user models** for you.
- You separate your system into:
    - **Predict worker** (critical, real time)
    - **Score worker** (heavy, can be delayed)
    - **Report worker** (FastAPI, for UI and monitoring)

Use the navigation on the left to explore each part step by step.
