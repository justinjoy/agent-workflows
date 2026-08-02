# Installation

Install the `dev-workflows` plugin from this repository for Codex, Claude Code, or Antigravity.

The plugin skills can be installed without the Python harness, but the
Datalog-based selector command requires the Python package. Installing the
project also installs `pyrewire>=1.0.4,<2.0`:

```bash
python3 -m pip install -e ".[dev]"
agent-workflows-harness --property trivial
```

Supported PyreWire wheels include the Wirelog runtime. For a custom or
source-built PyreWire installation, set `WIRELOG_LIB` to the absolute path of a
compatible `libwirelog` only when overriding library discovery is necessary.

## Codex

Add this repository as a Codex plugin marketplace from GitHub:

```bash
codex plugin marketplace add https://github.com/justinjoy/agent-workflows.git
```

Then install `dev-workflows` from the `agent-workflows` marketplace and start a new Codex session.

## Claude Code

Add this repository as a Claude Code plugin marketplace:

```text
/plugin marketplace add https://github.com/justinjoy/agent-workflows.git
/plugin install dev-workflows@agent-workflows
```

After installing, run `/reload-plugins` or start a new Claude Code session. Plugin skills are namespaced, so the implementation workflow is invoked as:

```text
/dev-workflows:implementation-skill
```

## Antigravity

Add this repository as an Antigravity plugin marketplace:

```bash
agy plugin marketplace add https://github.com/justinjoy/agent-workflows.git
```

Or within an Antigravity session (CLI or IDE):

```text
/plugin marketplace add https://github.com/justinjoy/agent-workflows.git
/plugin install dev-workflows@agent-workflows
```

After installing, the implementation workflow can be invoked as:

```text
/dev-workflows:implementation-skill
```

or directly by skill name:

```text
implementation-skill
```
