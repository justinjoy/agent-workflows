from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from .models import SkillPlan

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers only
    from .ontology import Derivation


def plan_to_dict(plan: SkillPlan, derivations: "Sequence[Derivation]" = ()) -> dict:
    """Convert a skill plan into stable JSON-compatible data.

    ``derivations`` records how ontology-backed facts were inferred. The key is
    omitted when empty so keyword-classified output stays byte-identical.
    """

    data = {
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
    if derivations:
        data["derived"] = [item.to_dict() for item in derivations]
    return data
