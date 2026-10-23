# Worker environment

Read by every Runway Agent worker before it builds a ticket in this repo. Keep it short and true.

## A fresh worktree lacks

- (e.g. `npm ci` before anything runs; a `.env` copied from `.env.example` with test values)

## Verify command

```bash
# the one command that must pass before build-done, e.g. npm test
```

## Leave alone

- (paths a worker must never edit, e.g. generated code, vendored packages)

## Workspace root

`~/runway-work/` unless a line here says otherwise.
