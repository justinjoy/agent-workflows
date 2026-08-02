# Agent Workflows

Shared agent skills for Codex, Claude Code, and Antigravity.

`implementation-skill` is now a Datalog-selected harness. It keeps the stable
host entrypoint, but splits implementation work into smaller atomic skills and
uses PyreWire/Wirelog rules to select the skill plan for each request.

## Included Skills

- `implementation-skill`: Datalog/PyreWire harness entrypoint that selects atomic implementation skills with explicit rules.
- `close-open-issues-goal`: persistent workflow for reducing open repository issues to zero.

## Harness CLI

Install the Python package when you want to run the selector locally. The
package requires PyreWire 1.0.4 or newer within the stable 1.x API line:

```bash
python3 -m pip install -e ".[dev]"
```

Then select a skill plan:

```bash
agent-workflows-harness "refactor auth workflow and add tests"
```

The command emits JSON with request facts, selected skills, blocked skills, and
rule reasons. Add `--decision-log path/to/decisions.jsonl` to append a durable
selection record for the run.

Supported PyreWire wheels include the Wirelog runtime. `WIRELOG_LIB` is only
needed to override the bundled library or when using a custom/source-built
PyreWire installation.

## Docs

- [How it works](docs/how-it-works.md)
- [Installation](docs/installation.md)
- [Maintenance](docs/maintenance.md)

## License

APACHE-2.0
