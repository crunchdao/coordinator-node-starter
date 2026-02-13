# extensions (node-private)

Use this folder for **node-specific callable overrides**.

Most customization should go in `runtime_definitions/contracts.py`
by overriding fields on the `CrunchContract`.

This folder is for edge cases where you need additional Python
modules available to the runtime (e.g., custom feed providers,
specialized scoring helpers).
