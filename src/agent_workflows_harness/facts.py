from __future__ import annotations

import re

from .models import RequestFacts


_PROPERTY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("non_trivial", ("refactor", "migration", "migrate", "redesign", "architecture")),
    ("multi_file", ("multi-file", "multiple files", "across modules", "shared")),
    ("needs_tests", ("test", "tests", "coverage", "regression")),
    ("needs_review", ("review", "pr feedback", "requested changes")),
    ("touches_shared_behavior", ("shared behavior", "public api", "workflow", "auth", "persistence")),
    ("external_service", ("api", "database", "db", "github", "gmail", "network")),
    ("docs_only", ("docs only", "documentation only", "readme only")),
)


def classify_request(text: str) -> RequestFacts:
    """Make conservative request facts from plain text without using an LLM."""

    normalized = re.sub(r"\s+", " ", text.casefold())
    properties: set[str] = set()
    for prop, keywords in _PROPERTY_KEYWORDS:
        if any(_contains_phrase(normalized, keyword) for keyword in keywords):
            properties.add(prop)

    # In docs-only text, names such as "GitHub", "API", or "auth workflow"
    # describe documentation subjects rather than evidence of runtime impact.
    # Explicit properties remain strict and are validated by RequestFacts.
    if "docs_only" in properties:
        properties.difference_update({"external_service", "touches_shared_behavior"})

    if any(
        _contains_phrase(normalized, keyword)
        for keyword in ("small", "trivial", "typo", "one-line")
    ):
        properties.add("trivial")
    if _contains_phrase(normalized, "commit"):
        properties.add("needs_commit")

    if "trivial" not in properties and "docs_only" not in properties:
        properties.add("non_trivial")

    return RequestFacts.from_properties(properties)


def _contains_phrase(text: str, phrase: str) -> bool:
    """Match a keyword as a token/phrase instead of as an arbitrary substring."""

    escaped = re.escape(phrase).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![\w-]){escaped}(?![\w-])", text) is not None


def format_fact_lines(facts: RequestFacts) -> str:
    lines = [
        f'request("{facts.request_id}").',
        f'request_type("{facts.request_id}", "{facts.request_type}").',
    ]
    for prop in sorted(facts.properties):
        lines.append(f'property("{facts.request_id}", "{prop}").')
    return "\n".join(lines)
