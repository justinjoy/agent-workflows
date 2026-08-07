from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .models import SUPPORTED_PROPERTIES


_TERM_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,127}\Z")

#: Class whose individuals describe documentation surfaces. A request that
#: touches only these is documentation-only.
DOC_SURFACE = "DocSurface"


@dataclass(frozen=True)
class Ontology:
    """A TBox describing surfaces, skills, and the request facts they imply.

    The harness stays deterministic and LLM-free: an LLM may propose the ABox
    triples that reach the CLI, but every property derived from them comes from
    these declared classes and the Wirelog closure over them.
    """

    sub_class_of: tuple[tuple[str, str], ...]
    surface_class: tuple[tuple[str, str], ...]
    skill_class: tuple[tuple[str, str], ...]
    property_of_class: tuple[tuple[str, str], ...]
    scope_property: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        for label, pairs in (
            ("sub_class_of", self.sub_class_of),
            ("surface_class", self.surface_class),
            ("skill_class", self.skill_class),
            ("property_of_class", self.property_of_class),
            ("scope_property", self.scope_property),
        ):
            for pair in pairs:
                if len(pair) != 2 or not all(isinstance(term, str) for term in pair):
                    raise ValueError(f"{label} entries must be pairs of strings")
                for term in pair:
                    if not _TERM_PATTERN.fullmatch(term):
                        raise ValueError(
                            f"{label} term {term!r} must start with a letter and "
                            "contain only letters, digits, '_', or '-'"
                        )

        unknown = {prop for _, prop in self.property_of_class} - SUPPORTED_PROPERTIES
        unknown |= {prop for _, prop in self.scope_property} - SUPPORTED_PROPERTIES
        if unknown:
            values = ", ".join(repr(prop) for prop in sorted(unknown))
            raise ValueError(f"ontology maps unsupported request properties: {values}")

        declared = self.classes()
        undeclared = {cls for _, cls in self.surface_class} - declared
        undeclared |= {cls for _, cls in self.skill_class} - declared
        undeclared |= {cls for cls, _ in self.property_of_class} - declared
        if undeclared:
            values = ", ".join(repr(cls) for cls in sorted(undeclared))
            raise ValueError(f"ontology references undeclared classes: {values}")

        self._reject_cycles()

    def _reject_cycles(self) -> None:
        parents: dict[str, list[str]] = {}
        for sub, sup in self.sub_class_of:
            parents.setdefault(sub, []).append(sup)

        # WHITE/GREY/BLACK walk: a GREY node reached again closes a cycle, which
        # would make the Wirelog closure meaningless rather than merely wrong.
        state: dict[str, int] = {}

        def visit(node: str, trail: tuple[str, ...]) -> None:
            if state.get(node) == 2:
                return
            if state.get(node) == 1:
                chain = " -> ".join((*trail, node))
                raise ValueError(f"ontology sub_class_of contains a cycle: {chain}")
            state[node] = 1
            for parent in parents.get(node, ()):
                visit(parent, (*trail, node))
            state[node] = 2

        for sub in sorted(parents):
            visit(sub, ())

    def classes(self) -> frozenset[str]:
        names: set[str] = set()
        for sub, sup in self.sub_class_of:
            names.add(sub)
            names.add(sup)
        for _, cls in self.skill_class:
            names.add(cls)
        return frozenset(names)

    def individuals(self) -> frozenset[str]:
        return frozenset(ind for ind, _ in self.surface_class)

    def scopes(self) -> frozenset[str]:
        return frozenset(scope for scope, _ in self.scope_property)

    def to_dict(self) -> dict:
        return {
            "sub_class_of": [list(pair) for pair in self.sub_class_of],
            "surface_class": [list(pair) for pair in self.surface_class],
            "skill_class": [list(pair) for pair in self.skill_class],
            "property_of_class": [list(pair) for pair in self.property_of_class],
            "scope_property": [list(pair) for pair in self.scope_property],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ontology":
        if not isinstance(data, dict):
            raise ValueError("ontology document must be a JSON object")
        unknown = set(data) - {
            "sub_class_of",
            "surface_class",
            "skill_class",
            "property_of_class",
            "scope_property",
        }
        if unknown:
            values = ", ".join(repr(key) for key in sorted(unknown))
            raise ValueError(f"ontology document has unsupported keys: {values}")

        def pairs(key: str) -> tuple[tuple[str, str], ...]:
            rows = data.get(key, ())
            if isinstance(rows, (str, bytes)) or not hasattr(rows, "__iter__"):
                raise ValueError(f"ontology {key} must be a list of pairs")
            collected = []
            for row in rows:
                if isinstance(row, (str, bytes)) or not hasattr(row, "__iter__"):
                    raise ValueError(f"ontology {key} entries must be pairs")
                items = tuple(row)
                if len(items) != 2:
                    raise ValueError(f"ontology {key} entries must be pairs")
                collected.append((items[0], items[1]))
            return tuple(collected)

        return cls(
            sub_class_of=pairs("sub_class_of"),
            surface_class=pairs("surface_class"),
            skill_class=pairs("skill_class"),
            property_of_class=pairs("property_of_class"),
            scope_property=pairs("scope_property"),
        )


def load_ontology(path: str | Path) -> Ontology:
    """Read a TBox document from disk, replacing the bundled default."""

    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ontology file {path} is not valid JSON: {exc}") from exc
    return Ontology.from_dict(data)


DEFAULT_ONTOLOGY = Ontology(
    sub_class_of=(
        ("SharedBehavior", "Surface"),
        ("AuthSurface", "SharedBehavior"),
        ("PersistenceSurface", "SharedBehavior"),
        ("PublicApiSurface", "SharedBehavior"),
        ("ExternalServiceSurface", "Surface"),
        ("DocSurface", "Surface"),
        ("ContextSkill", "Skill"),
        ("RiskSkill", "Skill"),
        ("PlanningSkill", "Skill"),
        ("CritiqueSkill", "Skill"),
        ("ChangeSkill", "Skill"),
        ("ValidationSkill", "Skill"),
        ("TestSkill", "ValidationSkill"),
        ("FocusedTestSkill", "TestSkill"),
        ("BroadTestSkill", "TestSkill"),
        ("ReviewSkill", "ValidationSkill"),
        ("CommitSkill", "Skill"),
        ("ReportSkill", "Skill"),
    ),
    surface_class=(
        ("auth_module", "AuthSurface"),
        ("session_module", "AuthSurface"),
        ("token_module", "AuthSurface"),
        ("login_flow", "AuthSurface"),
        ("permission_check", "AuthSurface"),
        ("database_schema", "PersistenceSurface"),
        ("migration", "PersistenceSurface"),
        ("persistence_layer", "PersistenceSurface"),
        ("storage_adapter", "PersistenceSurface"),
        ("public_api", "PublicApiSurface"),
        ("cli_interface", "PublicApiSurface"),
        ("plugin_contract", "PublicApiSurface"),
        ("github_api", "ExternalServiceSurface"),
        ("gmail_api", "ExternalServiceSurface"),
        ("network_client", "ExternalServiceSurface"),
        ("readme", "DocSurface"),
        ("changelog", "DocSurface"),
        ("docs_page", "DocSurface"),
    ),
    skill_class=(
        ("inspect-repository", "ContextSkill"),
        ("classify-change-risk", "RiskSkill"),
        ("create-implementation-plan", "PlanningSkill"),
        ("critique-plan", "CritiqueSkill"),
        ("implement-atomic-change", "ChangeSkill"),
        ("run-focused-tests", "FocusedTestSkill"),
        ("run-broad-tests", "BroadTestSkill"),
        ("review-diff", "ReviewSkill"),
        ("validate-final-design", "ReviewSkill"),
        ("validate-final-risks", "ReviewSkill"),
        ("commit-atomic-change", "CommitSkill"),
        ("report-result", "ReportSkill"),
    ),
    property_of_class=(
        ("SharedBehavior", "touches_shared_behavior"),
        ("ExternalServiceSurface", "external_service"),
    ),
    scope_property=(
        ("one_line", "trivial"),
        ("single_file", "trivial"),
        ("several_files", "multi_file"),
        ("cross_module", "multi_file"),
    ),
)


@dataclass(frozen=True)
class Derivation:
    """One request property together with the ABox triple that produced it."""

    request_property: str
    source: str
    path: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "property": self.request_property,
            "from": self.source,
            "path": " -> ".join(self.path),
        }


def subsumption_path(ontology: Ontology, individual: str, target: str) -> tuple[str, ...]:
    """Return the shortest individual -> ... -> target chain for explanations."""

    parents: dict[str, list[str]] = {}
    for sub, sup in ontology.sub_class_of:
        parents.setdefault(sub, []).append(sup)

    starts = [cls for ind, cls in ontology.surface_class if ind == individual]
    queue: deque[tuple[str, ...]] = deque((individual, cls) for cls in sorted(starts))
    seen: set[str] = set(starts)
    while queue:
        chain = queue.popleft()
        if chain[-1] == target:
            return chain
        for parent in sorted(parents.get(chain[-1], ())):
            if parent in seen:
                continue
            seen.add(parent)
            queue.append((*chain, parent))
    return (individual, target)


_RULES = """
.decl sub_class_of(sub: int32, sup: int32)
.decl surface_class(ind: int32, cls: int32)
.decl property_of_class(cls: int32, prop: int32)
.decl scope_property(sc: int32, prop: int32)
.decl touches(req: int32, ind: int32)
.decl scope_fact(req: int32, sc: int32)
.decl isa(ind: int32, cls: int32)
.decl doc_touch(req: int32)
.decl non_doc_touch(req: int32)
.decl derived_surface_property(prop: int32, cls: int32, ind: int32)
.decl derived_scope_property(prop: int32, sc: int32)
.decl derived_docs_only(req: int32)

isa(I, C) :- surface_class(I, C).
isa(I, S) :- isa(I, C), sub_class_of(C, S).

derived_surface_property(P, C, I) :-
    touches(R, I),
    isa(I, C),
    property_of_class(C, P).

derived_scope_property(P, S) :-
    scope_fact(R, S),
    scope_property(S, P).

doc_touch(R) :- touches(R, I), isa(I, {doc_code}).
non_doc_touch(R) :- touches(R, I), !isa(I, {doc_code}).
derived_docs_only(R) :- doc_touch(R), !non_doc_touch(R).
"""


class _Symbols:
    """Deterministic string <-> int32 interning, matching the registry convention."""

    def __init__(self, ontology: Ontology) -> None:
        terms = set(ontology.classes()) | set(ontology.individuals())
        terms |= set(ontology.scopes())
        terms |= {prop for _, prop in ontology.property_of_class}
        terms |= {prop for _, prop in ontology.scope_property}
        terms.add(DOC_SURFACE)
        self._code_by_term = {term: index + 1 for index, term in enumerate(sorted(terms))}
        self._term_by_code = {code: term for term, code in self._code_by_term.items()}

    def code(self, term: str) -> int:
        return self._code_by_term[term]

    def term(self, code: int) -> str:
        return self._term_by_code[int(code)]

    def known(self, term: str) -> bool:
        return term in self._code_by_term


def build_program(
    ontology: Ontology,
    symbols: _Symbols,
    touches: tuple[str, ...],
    scopes: tuple[str, ...],
) -> str:
    lines = [_RULES.format(doc_code=symbols.code(DOC_SURFACE))]
    for sub, sup in ontology.sub_class_of:
        lines.append(f"sub_class_of({symbols.code(sub)}, {symbols.code(sup)}).")
    for ind, cls in ontology.surface_class:
        lines.append(f"surface_class({symbols.code(ind)}, {symbols.code(cls)}).")
    for cls, prop in ontology.property_of_class:
        lines.append(f"property_of_class({symbols.code(cls)}, {symbols.code(prop)}).")
    for scope, prop in ontology.scope_property:
        lines.append(f"scope_property({symbols.code(scope)}, {symbols.code(prop)}).")
    for individual in touches:
        lines.append(f"touches(1, {symbols.code(individual)}).")
    for scope in scopes:
        lines.append(f"scope_fact(1, {symbols.code(scope)}).")
    return "\n".join(lines) + "\n"


def derive(
    touches: tuple[str, ...] | list[str],
    scopes: tuple[str, ...] | list[str] = (),
    ontology: Ontology | None = None,
) -> tuple[Derivation, ...]:
    """Evaluate the TBox closure over ABox triples and return derived properties."""

    from pyrewire import BatchProgram

    active = ontology or DEFAULT_ONTOLOGY
    symbols = _Symbols(active)

    touched = tuple(touches)
    scoped = tuple(scopes)
    for individual in touched:
        if not symbols.known(individual) or individual not in active.individuals():
            raise ValueError(
                f"unknown surface {individual!r}; declare it in the ontology "
                "surface_class before using it as a fact"
            )
    for scope in scoped:
        if scope not in active.scopes():
            raise ValueError(
                f"unknown scope {scope!r}; declare it in the ontology scope_property"
            )
    if not touched and not scoped:
        return ()

    program_text = build_program(active, symbols, touched, scoped)
    with BatchProgram.from_string(program_text) as program:
        program.optimize()
        program.load_all_facts()
        result = program.evaluate()
        try:
            # Reading an empty relation is an execution error, so gate every
            # read on cardinality the way the skill selector does.
            def rows(name: str) -> list[tuple]:
                if result.cardinality(name) <= 0:
                    return []
                return [tuple(row) for row in result.relation(name)]

            surface_rows = rows("derived_surface_property")
            scope_rows = rows("derived_scope_property")
            docs_only = result.cardinality("derived_docs_only") > 0
        finally:
            result.close()

    derivations: dict[tuple[str, str], Derivation] = {}
    for prop_code, cls_code, ind_code in surface_rows:
        prop = symbols.term(prop_code)
        cls = symbols.term(cls_code)
        individual = symbols.term(ind_code)
        derivations[(prop, individual)] = Derivation(
            request_property=prop,
            source=f"touches(req, {individual})",
            path=subsumption_path(active, individual, cls),
        )
    for prop_code, scope_code in scope_rows:
        prop = symbols.term(prop_code)
        scope = symbols.term(scope_code)
        derivations[(prop, scope)] = Derivation(
            request_property=prop,
            source=f"scope(req, {scope})",
            path=(scope, prop),
        )
    if docs_only:
        touched_docs = ", ".join(sorted(touched))
        derivations[("docs_only", DOC_SURFACE)] = Derivation(
            request_property="docs_only",
            source=f"touches(req, {touched_docs})",
            path=(DOC_SURFACE, "docs_only"),
        )

    return tuple(
        sorted(
            derivations.values(),
            key=lambda item: (item.request_property, item.source),
        )
    )


def derived_properties(
    touches: tuple[str, ...] | list[str],
    scopes: tuple[str, ...] | list[str] = (),
    ontology: Ontology | None = None,
) -> frozenset[str]:
    """Return only the property names implied by the ABox triples."""

    return frozenset(item.request_property for item in derive(touches, scopes, ontology))
