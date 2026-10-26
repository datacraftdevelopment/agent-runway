# Contributing to Agent Runway

Bugs and ideas are welcome as [issues](https://github.com/datacraftdevelopment/agent-runway/issues/new/choose). This
repository is public: leave out secrets, tokens, private repo names and anyone else's code.

## Pull requests

Before a pull request can be merged, its author accepts the [Contributor Licence Agreement](CLA.md). A check on the
pull request asks for it the first time you open one: reply with the sentence it gives you and the check goes green.
You only do this once.

Why: Agent Runway is free and source available under the [PolyForm Shield licence](LICENSE), and DataCraft Development
may also offer it under other terms later, such as a paid edition. The agreement lets your contribution go into every
edition, while you keep your copyright. The skills vendored from Superpowers (listed in `plugin/agent-runway/VENDOR.md`)
stay MIT: a change to them is under MIT, not the agreement.

Keep a pull request to one change, say what it does and how you checked it, and run the tests the area has
(`python3 -m unittest` for the `runway` command, `swift test` in `app/`).
