"""Explicit, order-independent composition of local ontology data packs."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import Iterable

from .models import SUPPORTED_PROPERTIES
from .ontology import DEFAULT_ONTOLOGY, Ontology, RelationSource, _TERM_PATTERN

RELATIONS = ("sub_class_of", "surface_class", "skill_class", "property_of_class", "scope_property")
BUILTIN_PACKS = ("data-change", "deployment", "security")


@dataclass(frozen=True)
class OntologyPack:
    id: str
    schema_version: int
    requires: tuple[str, ...]
    relations: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    source: str

    @classmethod
    def from_dict(cls, data: dict, *, source: str) -> "OntologyPack":
        """Check local structure now; resolve references only after composition."""
        try:
            if not isinstance(data, dict) or set(data) != {"id", "schema_version", "requires", "ontology"}:
                raise ValueError("pack must contain exactly id, schema_version, requires, ontology")
            pack_id = data["id"]
            if not isinstance(pack_id, str) or not _TERM_PATTERN.fullmatch(pack_id):
                raise ValueError("pack id must be a well-formed ontology term")
            if type(data["schema_version"]) is not int or data["schema_version"] != 1:
                raise ValueError(f"pack {pack_id!r}: unsupported schema_version {data['schema_version']!r}")
            requires = data["requires"]
            if not isinstance(requires, list) or any(
                not isinstance(dep, str) or not _TERM_PATTERN.fullmatch(dep) for dep in requires
            ):
                raise ValueError(f"pack {pack_id!r}: requires must be a list of pack IDs")
            ontology = data["ontology"]
            if not isinstance(ontology, dict) or set(ontology) - set(RELATIONS):
                raise ValueError(f"pack {pack_id!r}: ontology must contain only TBox relations")
            relations = []
            for name in RELATIONS:
                rows = ontology.get(name, [])
                if not isinstance(rows, list):
                    raise ValueError(f"pack {pack_id!r}: {name} must be a list of pairs")
                normalized = set()
                for row in rows:
                    if not isinstance(row, list) or len(row) != 2 or any(
                        not isinstance(term, str) or not _TERM_PATTERN.fullmatch(term) for term in row
                    ):
                        raise ValueError(f"pack {pack_id!r}: malformed {name} pair {row!r}")
                    if name in {"property_of_class", "scope_property"} and row[1] not in SUPPORTED_PROPERTIES:
                        raise ValueError(f"pack {pack_id!r}: unsupported request property {row[1]!r}")
                    normalized.add(tuple(row))
                relations.append((name, tuple(sorted(normalized))))
            return cls(pack_id, 1, tuple(sorted(set(requires))), tuple(relations), source)
        except ValueError as exc:
            raise ValueError(f"{source}: {exc}") from exc

    def definition(self) -> tuple:
        return self.schema_version, self.requires, self.relations


@dataclass(frozen=True)
class OntologyComposition:
    ontology: Ontology
    base_source: str
    packs: tuple[OntologyPack, ...]

    def to_dict(self) -> dict:
        return {
            "base": {"provider": "base", "source": self.base_source},
            "packs": [
                {"id": pack_id, "provider": f"pack:{pack_id}",
                 "schema_version": group[0].schema_version,
                 "requires": list(group[0].requires),
                 "sources": sorted({pack.source for pack in group})}
                for pack_id, group in self._groups().items()
            ],
            "relations": [row.to_dict() for row in self.ontology.sources],
        }

    def _groups(self) -> dict[str, list[OntologyPack]]:
        return {pack_id: [p for p in self.packs if p.id == pack_id]
                for pack_id in sorted({p.id for p in self.packs})}


def load_pack(name_or_path: str | Path) -> OntologyPack:
    name = str(name_or_path)
    if name in BUILTIN_PACKS:
        source = f"builtin:{name}"
        text = files("agent_workflows_harness").joinpath("ontology_packs", name + ".json").read_text(encoding="utf-8")
    else:
        source = str(Path(name).resolve())
        try:
            text = Path(name).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"pack {source}: {exc}") from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"pack {source}: invalid JSON: {exc}") from exc
    return OntologyPack.from_dict(data, source=source)


def list_builtin_packs() -> list[dict]:
    return [{"id": p.id, "schema_version": p.schema_version, "requires": list(p.requires),
             "surfaces": sorted({left for name, rows in p.relations if name == "surface_class" for left, _ in rows})}
            for p in (load_pack(name) for name in BUILTIN_PACKS)]


def compose_ontology(
    packs: Iterable[OntologyPack],
    base: Ontology = DEFAULT_ONTOLOGY,
    *,
    base_source: str = "bundled default",
) -> OntologyComposition:
    """Union supplied packs over a base. Dependencies never activate other packs."""
    supplied = tuple(sorted(set(packs), key=lambda p: (p.id, p.source, p.definition())))
    grouped: dict[str, list[OntologyPack]] = {}
    for pack in supplied:
        grouped.setdefault(pack.id, []).append(pack)
    for pack_id, group in grouped.items():
        if len({p.definition() for p in group}) != 1:
            raise ValueError(f"conflicting definitions for pack {pack_id!r}: " + ", ".join(p.source for p in group))
    active = {pack_id: group[0] for pack_id, group in grouped.items()}
    complete: set[str] = set()

    def visit(pack_id: str, trail: tuple[str, ...]) -> None:
        if pack_id in trail:
            cycle = (*trail, pack_id)
            raise ValueError("pack dependency cycle: " + " -> ".join(
                f"{item} ({active[item].source})" for item in cycle))
        if pack_id in complete:
            return
        pack = active[pack_id]
        for dependency in pack.requires:
            if dependency not in active:
                raise ValueError(f"pack {pack_id!r} ({pack.source}) requires missing pack {dependency!r}; supply it explicitly")
            visit(dependency, (*trail, pack_id))
        complete.add(pack_id)

    for pack_id in active:
        visit(pack_id, ())
    if not supplied:
        return OntologyComposition(base, base_source, ())
    providers: dict[tuple[str, str, str], set[str]] = {}
    for name in RELATIONS:
        for left, right in getattr(base, name):
            providers.setdefault((name, left, right), set()).add("base")
    for pack in active.values():
        for name, rows in pack.relations:
            for left, right in rows:
                providers.setdefault((name, left, right), set()).add(f"pack:{pack.id}")
    relations = {name: tuple(sorted((left, right) for relation, left, right in providers if relation == name))
                 for name in RELATIONS}
    try:
        ontology = Ontology(**relations)
    except ValueError as exc:
        context = ", ".join(f"{p.id} ({p.source})" for p in supplied)
        raise ValueError(f"composition of base {base_source!r} and packs [{context}]: {exc}") from exc
    sources = tuple(RelationSource(*key, tuple(sorted(values))) for key, values in sorted(providers.items()))
    return OntologyComposition(replace(ontology, sources=sources), base_source, supplied)
