from __future__ import annotations

from dataclasses import dataclass, field
import re


SUPPORTED_REQUEST_TYPES = frozenset({"code_change"})
SUPPORTED_PROPERTIES = frozenset(
    {
        "docs_only",
        "external_service",
        "multi_file",
        "needs_commit",
        "needs_review",
        "needs_tests",
        "non_trivial",
        "touches_shared_behavior",
        "trivial",
    }
)
_NON_TRIVIAL_PROPERTIES = frozenset(
    {"external_service", "multi_file", "non_trivial", "touches_shared_behavior"}
)
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")


@dataclass(frozen=True)
class SkillDefinition:
    """A small executable workflow unit known to the harness."""

    skill_id: str
    order: int
    title: str
    output: str


@dataclass(frozen=True)
class RequestFacts:
    """Facts the selector evaluates for one agent run."""

    request_id: str = "req"
    request_type: str = "code_change"
    properties: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not _REQUEST_ID_PATTERN.fullmatch(
            self.request_id
        ):
            raise ValueError(
                "request_id must start with a letter and contain only letters, "
                "digits, '.', '_', ':', or '-'"
            )
        if self.request_type not in SUPPORTED_REQUEST_TYPES:
            supported = ", ".join(sorted(SUPPORTED_REQUEST_TYPES))
            raise ValueError(
                f"unsupported request_type {self.request_type!r}; expected one of: {supported}"
            )

        properties = frozenset(self.properties)
        if not all(isinstance(prop, str) for prop in properties):
            raise ValueError("request properties must be strings")
        unknown = properties - SUPPORTED_PROPERTIES
        if unknown:
            values = ", ".join(repr(prop) for prop in sorted(unknown))
            raise ValueError(f"unsupported request properties: {values}")

        # Concrete risk evidence wins over a caller's optimistic `trivial` hint.
        if "trivial" in properties and properties & _NON_TRIVIAL_PROPERTIES:
            properties = properties - {"trivial"}
        object.__setattr__(self, "properties", properties)

    @classmethod
    def from_properties(
        cls,
        properties: set[str] | frozenset[str],
        *,
        request_id: str = "req",
        request_type: str = "code_change",
    ) -> "RequestFacts":
        return cls(
            request_id=request_id,
            request_type=request_type,
            properties=frozenset(properties),
        )


@dataclass(frozen=True)
class SelectedSkill:
    """A skill selected by Wirelog, including the rule-level reason."""

    order: int
    skill_id: str
    reason: str


@dataclass(frozen=True)
class BlockedSkill:
    """A skill rejected by Wirelog, including the blocking rule reason."""

    skill_id: str
    reason: str


@dataclass(frozen=True)
class SkillPlan:
    """Machine-readable harness output for one request."""

    request: RequestFacts
    selected: tuple[SelectedSkill, ...]
    blocked: tuple[BlockedSkill, ...]
