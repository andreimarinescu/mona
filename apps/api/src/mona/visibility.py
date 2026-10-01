"""C9 §3.1 `visible(row, channel)`: the one filter behind MCP tools, the brief, REST and exports.

Invisible rows behave as absent. Visitors documents are listed on `web` but left out of every
figure (sums, the brief, deadlines, reminders) on every channel (§5.5)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import and_, exists, or_, select, true
from sqlalchemy.ext.asyncio import AsyncConnection

from mona.db.models import (
    Account,
    Batch,
    Deadline,
    Document,
    Entity,
    EntityPerson,
    Person,
    SubUnit,
)

Channel = Literal["web", "telegram", "export"]


@dataclass
class Scope:
    conn: AsyncConnection
    channel: Channel
    hidden_entities: frozenset[str]
    visitors: str | None = None

    def entity_visible(self, entity_id: str | None) -> bool:
        return entity_id is None or entity_id not in self.hidden_entities

    def visible_entity_clause(self, column: Any) -> Any:
        """SQL: rows whose entity column is null or visible on this channel."""
        if not self.hidden_entities:
            return true()
        return column.is_(None) | column.not_in(self.hidden_entities)

    def document_clauses(self, doc: Any = Document) -> list[Any]:
        """A document row: not deleted; on `telegram` also an entity that is set, not personal
        and not Visitors (§3.1)."""
        out = [doc.deleted_at.is_(None)]
        if self.channel == "telegram":
            out.append(doc.entity_id.is_not(None))
            if self.hidden_entities:
                out.append(doc.entity_id.not_in(self.hidden_entities))
        return out

    def document_visible(self, doc: Mapping[str, Any]) -> bool:
        """`document_clauses` on a fetched document row; keep the two in step."""
        if doc["deleted_at"] is not None:
            return False
        if self.channel == "telegram":
            return doc["entity_id"] is not None and doc["entity_id"] not in self.hidden_entities
        return True

    def figures_clauses(self, doc: Any = Document) -> list[Any]:
        """Left out of every figure on every channel: documents of a visitor batch (§5.5)."""
        visitor_batch = exists().where(Batch.id == doc.batch_id, Batch.visitor.is_(True))
        out = [~visitor_batch]
        if self.visitors is not None:
            out.append(doc.entity_id.is_distinct_from(self.visitors))
        return out

    def deadline_clauses(self, doc: Any = Document) -> list[Any]:
        """A deadline row (outer-joined to its document as `doc`): its entity visible and not
        Visitors; its document, if any, not deleted, visible, and not a Visitors one."""
        out = [self.visible_entity_clause(Deadline.entity_id)]
        if self.visitors is not None:
            out.append(Deadline.entity_id != self.visitors)
        visible_doc = and_(*self.document_clauses(doc), *self.figures_clauses(doc))
        out.append(or_(Deadline.document_id.is_(None), visible_doc))
        return out


async def visitors_entity(conn: AsyncConnection) -> str | None:
    return (
        await conn.execute(select(Entity.id).where(Entity.purge_after_hours.is_not(None)))
    ).scalar()


async def scope_for(conn: AsyncConnection, ch: Channel) -> Scope:
    visitors = await visitors_entity(conn)
    hidden: frozenset[str] = frozenset()
    if ch == "telegram":
        personal = (
            (await conn.execute(select(Entity.id).where(Entity.visibility == "personal")))
            .scalars()
            .all()
        )
        hidden = frozenset(personal) | ({visitors} if visitors else frozenset())
    return Scope(conn, ch, hidden, visitors)


def export_clauses(entity_id: str, fiscal_year: int, doc: Any = Document) -> list[Any]:
    """§3.1 `export` column: the entity's filed, non-deleted documents of that fiscal year."""
    return [
        doc.deleted_at.is_(None),
        doc.status == "filed",
        doc.entity_id == entity_id,
        doc.fiscal_year == fiscal_year,
    ]


async def exportable(conn: AsyncConnection, entity_id: str) -> bool:
    """Personal entities and the Visitors entity are refused on every channel (C4 §3.13)."""
    row = (
        await conn.execute(
            select(Entity.visibility, Entity.purge_after_hours).where(Entity.id == entity_id)
        )
    ).first()
    return row is not None and row.visibility == "practice" and row.purge_after_hours is None


@dataclass
class RuleVisibility:
    """C4 §2.6 rules: hidden when the action or any condition points at a hidden entity."""

    personal_keys: frozenset[str]
    personal_accounts: frozenset[str]
    personal_people: frozenset[str]

    def visible(self, conditions: list[dict[str, Any]], action: dict[str, Any]) -> bool:
        if action.get("entity") in self.personal_keys:
            return False
        for c in conditions:
            field, op, value = c.get("field"), c.get("op"), c.get("value")
            values = value if isinstance(value, list) else [value]
            if field == "entity" and any(v in self.personal_keys for v in values):
                return False
            if (field, op) in {("addressee", "is_entity"), ("iban", "entity"), ("siren", "entity")}:
                if value in self.personal_keys:
                    return False
            if (field, op) == ("iban", "account") and value in self.personal_accounts:
                return False
            if (field, op) in {("addressee", "is_person"), ("person", "mentions")}:
                if value in self.personal_people:
                    return False
        return True


async def rule_visibility(scope: Scope) -> RuleVisibility | None:
    """None on `web`, where every rule is visible."""
    if not scope.hidden_entities:
        return None
    conn, hidden = scope.conn, scope.hidden_entities
    keys = (await conn.execute(select(Entity.key).where(Entity.id.in_(hidden)))).scalars()
    accounts = (
        await conn.execute(select(Account.key).where(Account.entity_id.in_(hidden)))
    ).scalars()
    linked = select(EntityPerson.person_id).where(EntityPerson.entity_id.in_(hidden))
    units = select(SubUnit.person_id).where(
        SubUnit.entity_id.in_(hidden), SubUnit.person_id.is_not(None)
    )
    people = (
        await conn.execute(select(Person.key).where(Person.id.in_(linked.union(units))))
    ).scalars()
    return RuleVisibility(frozenset(keys), frozenset(accounts), frozenset(people))
