# Agent Workflows

Shared agent skills for Codex, Claude Code, and Antigravity.

## Layout

```text
.agents/plugins/marketplace.json
.claude-plugin/marketplace.json
.antigravity-plugin/marketplace.json
.gemini-plugin/marketplace.json
plugins/dev-workflows/
  .codex-plugin/plugin.json
  .claude-plugin/plugin.json
  .antigravity-plugin/plugin.json
  .gemini-plugin/plugin.json
  skills/
    implementation-skill/
      SKILL.md
      agents/openai.yaml
      agents/gemini.yaml
      agents/antigravity.yaml
    close-open-issues-goal/
      SKILL.md
      agents/openai.yaml
      agents/gemini.yaml
      agents/antigravity.yaml
```

The `skills/` directory is shared by all plugin manifests so each skill is maintained once.

## Codex

Add this repository as a Codex plugin marketplace from the repository root:

```bash
codex plugin marketplace add /Users/joykim/git/agent-workflows
```

Then install `dev-workflows` from the `agent-workflows` marketplace and start a new Codex session.

## Claude Code

Add this repository as a Claude Code plugin marketplace:

```text
/plugin marketplace add /Users/joykim/git/agent-workflows
/plugin install dev-workflows@agent-workflows
```

After installing, run `/reload-plugins` or start a new Claude Code session. Plugin skills are namespaced, so the implementation workflow is invoked as:

```text
/dev-workflows:implementation-skill
```

## Antigravity

Add this repository as an Antigravity plugin marketplace:

```bash
agy plugin marketplace add /Users/joykim/git/agent-workflows
```

Or within an Antigravity session (CLI or IDE):

```text
/plugin marketplace add /Users/joykim/git/agent-workflows
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

## Updating Skills

Update files under `plugins/dev-workflows/skills/`. Keep provider-specific metadata in the corresponding `.codex-plugin/`, `.claude-plugin/`, `.antigravity-plugin/`, or `.gemini-plugin/` manifest.

## License

APACHE-2.0
