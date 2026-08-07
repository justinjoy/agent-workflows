from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from .models import SkillPlan
from .serialization import plan_to_dict

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers only
    from .ontology import Derivation


def append_decision_record(
    path: str | Path,
    plan: SkillPlan,
    derivations: "Sequence[Derivation]" = (),
) -> None:
    """Append one durable harness decision record as JSON Lines."""

    record = {
        "event_type": "agent_workflow.skill_plan_selected",
        "recorded_at": datetime.now(UTC).isoformat(),
        "plan": plan_to_dict(plan, derivations),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True))
        fh.write("\n")
