# Maintenance

## Source of Truth

The skill content under `plugins/dev-workflows/skills/` is shared across all supported hosts. Update skill behavior there first, then adjust provider-specific metadata only when a host needs different discovery or invocation details.

## Updating Skills

Each skill should keep its main instructions in `SKILL.md`. Host-specific agent prompts belong in that skill's `agents/` directory.

When changing a skill:

- Keep the frontmatter name and description aligned with how users invoke the skill.
- Preserve host-neutral language unless a section is explicitly provider-specific.
- Update every provider agent prompt that depends on the changed workflow.
- Keep examples short enough to copy, but specific enough to show the expected invocation.

## Updating Plugin Metadata

Provider manifests live under `plugins/dev-workflows/` in the corresponding hidden plugin directories. Change them only for metadata, packaging, or host integration updates; do not duplicate skill instructions there.

Root marketplace files expose the plugin to each host. Update them when the plugin package location, display metadata, or marketplace entry changes.

## Validation

Before committing documentation or workflow changes:

- Confirm README links still resolve.
- Confirm install commands in `docs/installation.md` still match the supported hosts.
- Search for stale skill names or old invocation examples.
- Review the diff to ensure plugin manifests and skill files changed only when intended.
- Run `python tests/mutations.py` when you change a contract test or the
  behavior one pins. It deletes each behavior in the table and checks that the
  named test goes red; an entry reported `SURVIVED` is a tripwire that stopped
  catching its mutation, and an entry reported `STALE` is one the table can no
  longer evaluate. Neither is visible from a green suite. This repo has no CI,
  so this checklist is the only thing that causes it to be run.
- Know what that green covers before you trust it. The table currently holds
  **5 entries covering 4 tests**, so a clean run says nothing about any other
  test you may have changed. That figure is pinned by
  `tests/test_mutations.py`, so growing the table forces this line to be
  updated with it and the number here cannot go stale.
