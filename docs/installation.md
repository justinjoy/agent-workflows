# Installation

Install the `dev-workflows` plugin from this repository for Codex, Claude Code,
or Antigravity. The plugin provides the skills; the optional Python package
provides the Wirelog selector used by `implementation-skill`.

## Prerequisites

- Git and one supported host: Codex, Claude Code, or Antigravity.
- Python 3.11 or newer when using the Wirelog harness.

The skills can be installed without Python. If the harness is unavailable, the
implementation skill reports that condition and fails closed to the
non-trivial workflow instead of silently skipping planning and review gates.

## Install the Plugin

### Codex

Add this repository as a Codex plugin marketplace:

```bash
codex plugin marketplace add https://github.com/justinjoy/agent-workflows.git
```

Install `dev-workflows` from the `agent-workflows` marketplace, then start a new
Codex session. Invoke the implementation workflow with:

```text
$dev-workflows:implementation-skill
```

### Claude Code

Add the marketplace and install the plugin:

```text
/plugin marketplace add https://github.com/justinjoy/agent-workflows.git
/plugin install dev-workflows@agent-workflows
```

Run `/reload-plugins` or start a new Claude Code session, then invoke:

```text
/dev-workflows:implementation-skill
```

Claude Code discovers the shared skills directly from the plugin root
`skills/` directory, including `implementation-skill` and
`commit-atomic-change`. No Claude-specific copy of those skills is required.

The Claude plugin manifest uses the project release version `2.1.0`; the
marketplace intentionally omits a duplicate version so the manifest remains
the single version source.
Existing installations can fetch and activate this lifecycle update with:

```text
/plugin marketplace update agent-workflows
/plugin update dev-workflows@agent-workflows
/reload-plugins
```

Restart Claude Code instead of `/reload-plugins` when preferred. To validate a
local checkout before marketplace installation, run from the repository root:

```bash
claude plugin validate ./plugins/dev-workflows --strict
claude --plugin-dir ./plugins/dev-workflows
```

The second command starts an interactive session using the local plugin. Invoke
`/dev-workflows:implementation-skill` there to exercise the shared lifecycle;
this local check does not verify marketplace update propagation.

### Antigravity

Clone this repository, then install the Antigravity plugin from its package
root:

```bash
git clone https://github.com/justinjoy/agent-workflows.git
cd agent-workflows
agy plugin validate ./plugins/dev-workflows
agy plugin install ./plugins/dev-workflows
```

Start a new Antigravity session:

```bash
agy
```

Then open `/skills` to verify that the plugin's skills were discovered:

```text
/skills
```

Invoke the namespaced workflow with:

```text
/dev-workflows:implementation-skill
```

Antigravity discovers the official `plugin.json` at the installed package root
and loads the shared sibling `skills/` directory. The same
`implementation-skill` used by the other hosts therefore enforces focused
tests, independent review, Architect and Critic approval of the immutable
candidate, and a verified atomic commit. Installing the repository URL itself
is not used here because this repository is a multi-host monorepo and the
Antigravity plugin root is `plugins/dev-workflows`.

## Install the Wirelog Harness

The Wirelog selector is evaluated through PyreWire. From a checkout of this
repository, create an isolated environment and install the runtime package.

On POSIX:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/agent-workflows-harness --property trivial
```

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\agent-workflows-harness.exe --property trivial
```

Installing the package also installs `pyrewire>=1.0.4,<2.0`. Contributors who
need the test and build dependencies can install `-e ".[dev]"` instead.

When running the skill in a different repository, either expose
`agent-workflows-harness` on the plugin host's `PATH`, or install this package
into that repository's existing `.venv`. The skill does not create an
environment or install the package on the user's behalf.

## Harness Command Resolution

A plugin host resolves the harness in this order:

1. Run `agent-workflows-harness` when it is on `PATH`.
2. Run `<workspace>/.venv/bin/agent-workflows-harness` on POSIX, or
   `<workspace>/.venv/Scripts/agent-workflows-harness.exe` on Windows, when the
   file exists and is executable.
3. Run `python -m agent_workflows_harness.cli` when the active Python can import
   the package.

Here, `<workspace>` is the root of the repository currently being worked on,
not the plugin installation directory. Its `.venv` must already contain the
harness package. A missing bare command does not make the runtime unavailable;
the host tries the remaining installed forms first. It does not create a
virtual environment, install dependencies, or rewrite the host environment
automatically.

Supported PyreWire wheels include the Wirelog runtime. For a custom or
source-built PyreWire installation, set `WIRELOG_LIB` to the absolute path of a
compatible `libwirelog` only when overriding library discovery is necessary.

## Smoke Test

Run a documentation-only request through the selector. For example, from the
POSIX checkout used above:

```bash
.venv/bin/agent-workflows-harness "documentation only: write an installation guide"
```

On other installations, use the first command form available from
[Harness Command Resolution](#harness-command-resolution).

The JSON response should classify the request with the `docs_only` property and
select these atomic skills:

1. `inspect-repository`
2. `classify-change-risk`
3. `implement-atomic-change`
4. `run-focused-tests`
5. `review-diff`
6. `validate-final-design`
7. `validate-final-risks`
8. `commit-atomic-change`
9. `report-result`

Planning, critique, and broad tests should be listed as blocked because a
documentation-only request has no additional risk facts. Review, final
Architect and Critic validation, and an atomic commit remain mandatory. This
confirms that Wirelog, through PyreWire, selected the documentation workflow
rather than relying on free-form skill choice.
