from __future__ import annotations

from .models import SkillPlan


def plan_to_dict(plan: SkillPlan) -> dict:
    """Convert a skill plan into stable JSON-compatible data."""

    return {
        "request": {
            "request_id": plan.request.request_id,
            "request_type": plan.request.request_type,
            "properties": sorted(plan.request.properties),
        },
        "selected": [
            {
                "order": skill.order,
                "skill_id": skill.skill_id,
                "reason": skill.reason,
            }
            for skill in plan.selected
        ],
        "blocked": [
            {
                "skill_id": skill.skill_id,
                "reason": skill.reason,
            }
            for skill in plan.blocked
        ],
    }
