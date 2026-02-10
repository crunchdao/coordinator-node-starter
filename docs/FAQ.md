# FAQ

A few common questions and short answers.

---

### My model does not appear in the game

Check the submission and the configuration by following the explanation in [Local Models](/RUNNING_LOCALLY/#local-models).

Check the orchestrator logs to verify if the model was started. Relevant error logs should be available there.


### Can everything run on a single machine?

Yes, especially at the beginning.

You can run:

- orchestrator (only during development phase),
- workers,
- database,

on a single machine using Docker.

As things grow, you can move each part to dedicated machines.

---

### Do I have to care about Web3 details?

Not for the game logic.

Web3 is used mainly for:

- identity,
- signatures,
- protocol-level rules.

You can get help to set up a coordinator wallet and node.
Your focus is on:

- talking to models,
- scoring them,
- exposing metrics.
