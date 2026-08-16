# Agent Workflows

Shared agent skills for Codex, Claude Code, and Antigravity.

`implementation-skill` is now a Wirelog-based harness evaluated through
PyreWire. It keeps the stable host entrypoint, but splits implementation work
into smaller atomic skills and uses explicit rules to select the skill plan for
each request.

Every change, including documentation, is validated, independently reviewed,
approved by Architect and Critic, and committed as an atomic unit. Every run
reports its result, including a run a gate rejects before any commit.

## Included Skills

- `implementation-skill`: Wirelog-based harness entrypoint that selects atomic implementation skills through PyreWire.
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

Requests can also be stated as ontology triples instead of prose. The harness
infers request properties from a declared class hierarchy, so a surface is
recognized by what it *is* rather than by the words used to describe it:

```bash
agent-workflows-harness --touches session_module --scope one_line
```

`session_module` contains none of the keywords the text classifier knows, yet
`AuthSurface ⊑ SharedBehavior` still selects planning, critique, and broad
tests. Each inferred property is reported with the subsumption path that
produced it. `--print-ontology` prints the vocabulary a request may draw on, so
a name for `--touches` or `--scope` is read rather than guessed. Use
`--ontology path/to/tbox.json` to supply your own TBox; adding vocabulary is a
data change rather than a code change, and the same flag shows what a supplied
file loaded as. See
[How it works](docs/how-it-works.md#ontology-fact-source).

Plugin hosts resolve the harness from `PATH`, the current workspace's `.venv`,
or an importable active Python environment, in that order. They try every
available form before treating the runtime as unavailable and do not install
dependencies or rewrite the host environment automatically. See
[Installation](docs/installation.md#harness-command-resolution) for the exact
commands.

Supported PyreWire wheels include the Wirelog runtime. `WIRELOG_LIB` is only
needed to override the bundled library or when using a custom/source-built
PyreWire installation.

## Docs

- [How it works](docs/how-it-works.md)
- [Installation](docs/installation.md)
- [Maintenance](docs/maintenance.md)

## License

APACHE-2.0
