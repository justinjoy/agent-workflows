from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .models import SkillPlan
from .serialization import plan_to_dict


def append_decision_record(path: str | Path, plan: SkillPlan) -> None:
    """Append one durable harness decision record as JSON Lines."""

    record = {
        "event_type": "agent_workflow.skill_plan_selected",
        "recorded_at": datetime.now(UTC).isoformat(),
        "plan": plan_to_dict(plan),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True))
        fh.write("\n")
