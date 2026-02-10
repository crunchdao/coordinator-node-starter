# FAQ

## Is this repo the final Crunch node?
No. This is the base template source.
Use it to create `crunch-node-<name>`.

## Where does crunch-specific logic live?
In callables configured from `crunch-<name>`.

## Can I add custom fields?
Yes. Default is JSONB extension fields in canonical tables.

## Why separate predict/score/report workers?
To isolate real-time model calls, heavy scoring, and API serving.
