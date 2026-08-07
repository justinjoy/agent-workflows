from __future__ import annotations

from .models import SkillDefinition


SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition("inspect-repository", 10, "Inspect repository", "repository_context"),
    SkillDefinition("classify-change-risk", 20, "Classify change risk", "risk_classification"),
    SkillDefinition(
        "create-implementation-plan",
        30,
        "Create implementation plan",
        "implementation_plan",
    ),
    SkillDefinition("critique-plan", 40, "Critique plan", "critique_findings"),
    SkillDefinition("implement-atomic-change", 50, "Implement atomic change", "code_diff"),
    SkillDefinition("run-focused-tests", 60, "Run focused tests", "focused_test_result"),
    SkillDefinition("run-broad-tests", 70, "Run broad tests", "broad_test_result"),
    SkillDefinition("review-diff", 80, "Review diff", "review_findings"),
    SkillDefinition("validate-final-design", 90, "Validate final design", "architect_validation"),
    SkillDefinition("validate-final-risks", 100, "Validate final risks", "critic_validation"),
    SkillDefinition("report-result", 110, "Report result", "final_report"),
    # Append new definitions so the positional Wirelog codes above remain stable.
    SkillDefinition("commit-atomic-change", 105, "Commit atomic change", "atomic_commit"),
)

SKILL_BY_ID = {skill.skill_id: skill for skill in SKILLS}
SKILL_CODE_BY_ID = {skill.skill_id: index + 1 for index, skill in enumerate(SKILLS)}
SKILL_ID_BY_CODE = {code: skill_id for skill_id, code in SKILL_CODE_BY_ID.items()}

#: Skill classes every code change selects, regardless of request facts. The
#: policy lives in one Wirelog rule; which skills belong to a class is data.
MANDATORY_SKILL_CLASSES: tuple[str, ...] = (
    "ContextSkill",
    "RiskSkill",
    "ChangeSkill",
    "ReviewSkill",
    "CommitSkill",
)

#: Skill classes selected only when the request needs an explicit plan.
PLANNED_SKILL_CLASSES: tuple[str, ...] = ("PlanningSkill", "CritiqueSkill")

#: Per-skill selection reasons for class-driven rules, which cannot carry a
#: single literal reason in the rule head.
SELECTION_REASON_BY_ID = {
    "inspect-repository": 1,
    "classify-change-risk": 2,
    "create-implementation-plan": 3,
    "critique-plan": 4,
    "implement-atomic-change": 5,
    "review-diff": 8,
    "validate-final-design": 9,
    "validate-final-risks": 10,
    "commit-atomic-change": 13,
}

#: Per-skill blocking reasons for the class-driven blocked-plan rule.
BLOCKING_REASON_BY_ID = {
    "create-implementation-plan": 101,
    "critique-plan": 102,
}

REASON_BY_CODE = {
    1: "code_change_requires_repository_context",
    2: "code_change_requires_risk_classification",
    3: "risk_or_scope_requires_explicit_plan",
    4: "planned_change_requires_plan_critique",
    5: "code_change_requires_atomic_implementation",
    6: "code_change_requires_focused_validation",
    7: "shared_or_cross_module_behavior_changed",
    8: "every_code_change_requires_review",
    9: "every_code_change_requires_architect_validation",
    10: "every_code_change_requires_critic_validation",
    11: "every_harness_run_reports_outcome",
    12: "documentation_change_requires_focused_validation",
    13: "every_code_change_requires_atomic_commit",
    101: "risk_facts_do_not_require_explicit_plan",
    102: "no_plan_selected",
    103: "no_shared_or_cross_module_behavior_fact",
    104: "review_gate_not_required",
    105: "no_explicit_plan_to_validate",
}
