# Condor-style Game Documentation

Welcome to this documentation.

This site explains how to build a **Condor-style prediction game** on top of the CrunchDAO protocol:

- You talk to **one model orchestrator**.
- The orchestrator runs **many user models** for you.
- You separate your system into:
    - **Predict worker** (critical, real time)
    - **Score worker** (heavy, can be delayed)
    - **Report worker** (FastAPI, for UI and monitoring)

<!-- TODO: rewrite this section in explain each section-->
Use the navigation on the left to explore each part step by step.
