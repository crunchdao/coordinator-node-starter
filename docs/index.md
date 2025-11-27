# Condor-style Game Documentation

Welcome to this documentation.

This site explains how to build a **Condor-style prediction game** on top of the CrunchDAO protocol:

- You talk to **one model orchestrator**.
- The orchestrator runs **many user models** for you.
- You separate your system into:
  - a **Predict worker** (critical, real time),
  - a **Score worker** (heavy, can be delayed),
  - a **Report worker** (FastAPI, for UI and monitoring).

Use the navigation on the left to explore each part step by step.
