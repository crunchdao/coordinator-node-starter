# Packs

Packs are overlay directories that customize `base/` for specific competition types.

## How it works

1. CLI copies `base/` to destination
2. If a pack is specified, copies `packs/<pack>/` on top (overwriting matching files)
3. Replaces `starter-challenge` → `<name>` and `starter_challenge` → `<module>` in all files

## Creating a pack

Add a directory here with only the files that differ from `base/`:

```
packs/
└── tournament/
    ├── node/
    │   └── .local.env.example     ← different schedule/config
    └── challenge/
        └── starter_challenge/
            ├── scoring.py          ← different scoring logic
            └── tracker.py          ← different model interface
```

Files not present in the pack inherit from `base/`.
