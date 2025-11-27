# FAQ

A few common questions and short answers.

---

### My model does not appear in the game

Check:

1. `deployment/config/models.dev.yaml` contains an entry for your model.
2. The `path` in that file matches a folder under `deployment/config/data/submission/`.
3. Your model implements the correct base class from the game repo.
4. `requirements.txt` installs without error.

Look at the orchestrator logs to see if the model was started.

---

### Predict worker crashes

Common causes:

- unhandled exceptions in your logic,
- blocking operations inside the async loop,
- database connection issues.

Check logs, isolate heavy work, and move it to the Score worker if needed.

---

### Scores do not update

Check:

- the Score worker is running,
- it can access the database or storage,
- the scoring loop is triggered (e.g. via a scheduler or a simple `while True`),
- your retention and window configuration are correct.

---

### Leaderboard is empty

Check:

- predictions are stored (see DB / storage),
- scores are produced and stored,
- Report worker is reading from the correct tables or files.

---

### Can I add new models while the game is running?

Yes.

As long as the orchestrator is configured to see them:

- in production: through the protocol and on-chain registration,
- in local mode: by updating `models.dev.yaml` and `submission/`.

The ModelRunner `sync()` keeps the list updated in real time.

---

### Can everything run on a single machine?

Yes, especially at the beginning.

You can run:

- orchestrator,
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
