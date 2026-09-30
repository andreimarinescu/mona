"""One read of the registry: rules-engine World, render inputs, names and rule specs."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, select

from mona.db.models import Base
from mona.rules.engine import (
    AccountRef,
    CounterpartyRef,
    EntityRef,
    PersonRef,
    RuleSpec,
    SubUnitRef,
    World,
)
from mona.rules.grammar import Condition, RuleAction
from mona.rules.text import Names
from mona.templates import EntityInfo

T = Base.metadata.tables


@dataclass
class Snapshot:
    settings: Mapping[str, Any]
    world: World
    names: Names
    entities: dict[str, Mapping[str, Any]] = field(default_factory=dict)  # key → row
    entity_keys: dict[str, str] = field(default_factory=dict)  # id → key
    sub_units: dict[tuple[str, str], Mapping[str, Any]] = field(default_factory=dict)
    sub_unit_keys: dict[str, tuple[str, str]] = field(default_factory=dict)  # id → (ent, key)
    people_keys: dict[str, str] = field(default_factory=dict)  # id → key
    counterparties: dict[str, Mapping[str, Any]] = field(default_factory=dict)  # key → row
    counterparty_keys: dict[str, str] = field(default_factory=dict)  # id → key
    categories: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    subcategories: dict[tuple[str, str], Mapping[str, Any]] = field(default_factory=dict)
    visitors: str | None = None

    @property
    def language(self) -> str:
        return self.settings["filing_language"]

    def entity_info(self, key: str | None) -> EntityInfo | None:
        if key is None:
            return None
        e = self.entities[key]
        return EntityInfo(
            e["key"], e["folder_name"], e["fy_end_month"], e["fy_end_day"], e["filing_language"]
        )

    def lang_for(self, entity_key: str | None) -> str:
        if entity_key and self.entities[entity_key]["filing_language"]:
            return self.entities[entity_key]["filing_language"]
        return self.language


def _spec(r: Mapping[str, Any]) -> RuleSpec:
    return RuleSpec(
        id=r["id"],
        priority=r["priority"],
        created_at=r["created_at"],
        conditions=tuple(Condition.model_validate(c) for c in r["conditions"]),
        action=RuleAction.model_validate(r["action"]),
        state=r["state"],
    )


def rule_specs(conn: Connection) -> list[RuleSpec]:
    return [_spec(r) for r in conn.execute(select(T["rules"])).mappings()]


def load(conn: Connection) -> Snapshot:
    settings = conn.execute(select(T["settings"])).mappings().one()
    ents = list(conn.execute(select(T["entities"])).mappings())
    people = list(conn.execute(select(T["people"])).mappings())
    subs = list(conn.execute(select(T["sub_units"])).mappings())
    accs = list(conn.execute(select(T["accounts"])).mappings())
    cps = list(conn.execute(select(T["counterparties"])).mappings())
    aliases: dict[str, list[str]] = {}
    for a in conn.execute(select(T["counterparty_aliases"])).mappings():
        aliases.setdefault(a["counterparty_id"], []).append(a["alias_norm"])
    cats = list(conn.execute(select(T["categories"])).mappings())
    subcats = list(conn.execute(select(T["subcategories"])).mappings())
    tpls = list(conn.execute(select(T["templates"])).mappings())

    ent_key = {e["id"]: e["key"] for e in ents}
    per_key = {p["id"]: p["key"] for p in people}
    world = World(
        people={
            p["key"]: PersonRef(p["key"], p["display_name"], tuple(p["aliases"])) for p in people
        },
        entities={
            e["key"]: EntityRef(e["key"], e["display_name"], tuple(e["aliases"]), e["siren"])
            for e in ents
        },
        accounts={
            a["key"]: AccountRef(a["key"], ent_key[a["entity_id"]], a["iban_hash"]) for a in accs
        },
        counterparties={
            c["key"]: CounterpartyRef(
                c["key"], c["name"], c["name_norm"], tuple(aliases.get(c["id"], ()))
            )
            for c in cps
        },
        iban_salt=bytes(settings["iban_salt"]),
    )
    for s in subs:
        world.sub_units.setdefault(ent_key[s["entity_id"]], []).append(
            SubUnitRef(ent_key[s["entity_id"]], s["key"], s["label"], per_key.get(s["person_id"]))
        )
    for sc in subcats:
        world.subcategories.setdefault(sc["category_id"], set()).add(sc["key"])
    for t in tpls:
        entity = ent_key.get(t["entity_id"]) if t["entity_id"] else None
        world.templates[(t["category_id"], entity)] = (t["path_template"], t["file_template"])
    names = Names(
        people={p["key"]: p["display_name"] for p in people},
        entities={e["key"]: e["display_name"] for e in ents},
        accounts={a["key"]: f"{a['label']} •• {a['iban_last4']}" for a in accs},
        categories={c["id"]: c["labels"] for c in cats},
    )
    return Snapshot(
        settings=settings,
        world=world,
        names=names,
        entities={e["key"]: e for e in ents},
        entity_keys=ent_key,
        sub_units={(ent_key[s["entity_id"]], s["key"]): s for s in subs},
        sub_unit_keys={s["id"]: (ent_key[s["entity_id"]], s["key"]) for s in subs},
        people_keys=per_key,
        counterparties={c["key"]: c for c in cps},
        counterparty_keys={c["id"]: c["key"] for c in cps},
        categories={c["id"]: c for c in cats},
        subcategories={(sc["category_id"], sc["key"]): sc for sc in subcats},
        visitors=next((e["key"] for e in ents if e["purge_after_hours"] is not None), None),
    )
