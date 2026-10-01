"""C2 §8 registry: entities, sub-units, accounts, people, categories, templates, counterparties.

Every write validates, then commits in one transaction; none moves a file."""

import re
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from sqlalchemy import Connection, delete, exists, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from mona import clock
from mona.api.deps import body_id, path_id, run
from mona.api.errors import ApiFailure, errors
from mona.api.models import (
    AccountWrite,
    CategoryList,
    CategoryPatch,
    CategoryWrite,
    EntityDetail,
    EntityList,
    EntityPatch,
    EntityPersonWrite,
    EntityWrite,
    PersonDetail,
    PersonList,
    PersonPatch,
    PersonWrite,
    SubcategoryPatch,
    SubcategoryWrite,
    SubUnitPatch,
    SubUnitWrite,
    TemplatePair,
    TemplatePreview,
    TemplatePreviewRequest,
)
from mona.db import get_sync_engine
from mona.dto.models import Category, Counterparty
from mona.iban import iban_hash, iban_last4, is_valid_iban, normalize_iban
from mona.ids import new_id
from mona.naming import to_camel
from mona.services import registry as reg
from mona.services.placement import render_values
from mona.services.registry import T
from mona.templates import (
    EntityInfo,
    NotRenderable,
    RenderValues,
    TemplateError,
    folder_segment,
    parse,
    render,
)
from mona.text import norm

router = APIRouter(prefix="/api", tags=["registry"])

EntityId = path_id("ent", "id")
SubUnitId = path_id("sub", "id")
AccountId = path_id("acc", "id")
PersonId = path_id("per", "id")
PersonPathId = path_id("per", "personId")
EntityPathId = path_id("ent", "entityId")

KEY = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
CATEGORY_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
SUBCATEGORY_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
LANGS = ("en", "fr", "ro")
ICONS = ("bank", "invoice", "tax", "insurance", "payroll", "training", "travel", "personal")
MONTH_DAYS = {2: 28, 4: 30, 6: 30, 9: 30, 11: 30}
VISITORS_FIELDS = {"display_name", "purge_after_hours"}
PURGE_HOURS = (1, 168)
COUNTERPARTY_LIMIT = 20
TRIGRAM_MIN = 0.2
SAMPLE = {
    "counterparty": "ACME",
    "reference": "2025-A-118",
    "doc_date": date(2026, 2, 27),
    "period_end": date(2025, 12, 31),
    "arrived_at": date(2026, 2, 27),
    "category": {"en": "Payment calls", "fr": "Appels de paiement", "ro": "Apeluri de plată"},
    "subcategory": {"en": "Contribution", "fr": "Cotisation", "ro": "Contribuție"},
}


def _conn() -> Connection:
    return get_sync_engine().connect()


def _tx() -> Any:
    return get_sync_engine().begin()


def invalid(field: str, message: str) -> ApiFailure:
    return ApiFailure(422, "invalid_value", message, field=field)


def duplicate(field: str) -> ApiFailure:
    return ApiFailure(409, "conflict", f"The {field} is already used.", field=field,
                      details={"reason": "duplicate"})  # fmt: skip


def not_found(what: str) -> ApiFailure:
    return ApiFailure(404, "not_found", f"No {what} with that id.")


def slugify(value: str, *, sep: str = "-") -> str:
    s = re.sub(r"[^a-z0-9]+", sep, norm(value)).strip(sep)
    s = re.sub(r"^[^a-z]+", "", s)[:40].rstrip(sep)
    return s if len(s) >= 2 else f"x{sep}{s}".rstrip(sep) if s else "item"


def free_key(conn: Connection, table: str, base: str, **scope: Any) -> str:
    t = T[table]
    taken = {
        k
        for (k,) in conn.execute(
            select(t.c.key).where(*(t.c[c] == v for c, v in scope.items()))
        ).all()
    }
    key, n = base, 2
    while key in taken:
        suffix = f"-{n}"
        key, n = base[: 40 - len(suffix)] + suffix, n + 1
    return key


def check_key(value: str | None, field: str = "key") -> None:
    if value is not None and not KEY.match(value):
        raise invalid(field, "Use a slug: a-z, 0-9 and '-', starting with a letter, 2-40 long.")


def check_labels(labels: dict[str, str], field: str = "labels") -> dict[str, str]:
    for lang in LANGS:
        value = labels.get(lang)
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise invalid(f"{field}.{lang}", "Give a label in en, fr and ro (1-120 characters).")
    extra = set(labels) - set(LANGS)
    if extra:
        raise invalid(f"{field}.{sorted(extra)[0]}", "Only en, fr and ro labels.")
    return {lang: labels[lang].strip() for lang in LANGS}


def check_templates(path_template: str, file_template: str) -> None:
    for kind, template in (("path", path_template), ("file", file_template)):
        try:
            parse(template, kind)  # type: ignore[arg-type]
        except TemplateError as e:
            raise ApiFailure(
                422, "invalid_template", "The template is invalid.",
                field=f"template.{kind}Template",
                details={"template": kind, "offset": e.offset, "message": e.message},
            ) from None  # fmt: skip


def fy_end(value: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{2})-(\d{2})", value)
    month, day = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    if not 1 <= month <= 12 or not 1 <= day <= MONTH_DAYS.get(month, 31):
        raise invalid("fiscalYearEnd", "Use a valid MM-DD fiscal-year end.")
    return month, day


def siren(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\s", "", value)
    if not re.fullmatch(r"\d{9}", digits):
        raise invalid("siren", "A SIREN has 9 digits.")
    return digits


def folder(value: str) -> str:
    if folder_segment(value) != value:
        raise invalid("folderName", "The folder name has characters a folder can't hold.")
    return value


# --- reads ---


def entity_dto(conn: Connection, row: Any) -> dict[str, Any]:
    s, ep, a = T["sub_units"], T["entity_people"], T["accounts"]
    subs = conn.execute(select(s).where(s.c.entity_id == row["id"]).order_by(s.c.key)).mappings()
    people = conn.execute(
        select(ep).where(ep.c.entity_id == row["id"]).order_by(ep.c.person_id)
    ).mappings()
    accounts = conn.execute(
        select(a).where(a.c.entity_id == row["id"]).order_by(a.c.key)
    ).mappings()
    return {
        "id": row["id"], "key": row["key"], "display_name": row["display_name"],
        "folder_name": row["folder_name"], "legal_form": row["legal_form"],
        "siren": row["siren"], "visibility": row["visibility"],
        "fiscal_year_end": f"{row['fy_end_month']:02d}-{row['fy_end_day']:02d}",
        "filing_language": row["filing_language"],
        "sub_units": [
            {"id": x["id"], "key": x["key"], "label": x["label"], "person_id": x["person_id"]}
            for x in subs
        ],
        "people": [{"person_id": x["person_id"], "role": x["role"]} for x in people],
        "accounts": [
            {"id": x["id"], "key": x["key"], "label": x["label"],
             "iban_last4": x["iban_last4"], "sub_unit_id": x["sub_unit_id"]}
            for x in accounts
        ],
    }  # fmt: skip


def entity_detail(conn: Connection, entity_id: str) -> dict[str, Any]:
    e = T["entities"]
    row = conn.execute(select(e).where(e.c.id == entity_id)).mappings().first()
    if row is None:
        raise not_found("entity")
    return {
        **entity_dto(conn, row),
        "aliases": list(row["aliases"]),
        "addresses": list(row["addresses"]),
        "purge_after_hours": row["purge_after_hours"],
        "sort_order": row["sort_order"],
    }


def _entities() -> dict[str, Any]:
    e, d = T["entities"], T["documents"]
    with _conn() as conn:
        rows = conn.execute(select(e).order_by(e.c.sort_order, e.c.display_name)).mappings().all()
        counts = dict(
            conn.execute(
                select(d.c.entity_id, func.count())
                .where(d.c.deleted_at.is_(None), d.c.entity_id.is_not(None))
                .group_by(d.c.entity_id)
            ).all()
        )
        return {
            "items": [entity_dto(conn, r) for r in rows],
            "document_counts": {r["id"]: counts.get(r["id"], 0) for r in rows},
            "visitors_entity_id": next(
                (r["id"] for r in rows if r["purge_after_hours"] is not None), None
            ),
        }


@router.get(
    "/entities", operation_id="listEntities", response_model=EntityList,
    responses=errors(401, 423),
)  # fmt: skip
async def list_entities() -> dict[str, Any]:
    return await run(_entities)


def _read_entity(entity_id: str) -> dict[str, Any]:
    with _conn() as conn:
        return entity_detail(conn, entity_id)


@router.get(
    "/entities/{id}", operation_id="getEntity", response_model=EntityDetail,
    responses=errors(401, 404, 423),
)  # fmt: skip
async def get_entity(entity_id: EntityId) -> dict[str, Any]:
    return await run(_read_entity, entity_id)


# --- entity writes ---


def _unique(err: IntegrityError) -> ApiFailure:
    constraint = getattr(getattr(err.orig, "diag", None), "constraint_name", "") or ""
    if constraint.endswith("_iban_hash_key"):
        return ApiFailure(
            409, "conflict", "That account exists already.", field="iban",
            details={"reason": "duplicate_account"},
        )  # fmt: skip
    for column, field in (("folder_name", "folderName"), ("label", "label"), ("key", "key")):
        if constraint.endswith(f"_{column}_key"):
            return duplicate(field)
    if constraint.endswith("_pkey"):
        return duplicate("id")
    raise err


def _entity_values(body: EntityWrite | EntityPatch, given: set[str]) -> dict[str, Any]:
    v: dict[str, Any] = {}
    if "key" in given:
        check_key(body.key)
        if body.key is not None:
            v["key"] = body.key
    for name in ("display_name", "legal_form", "visibility", "filing_language", "sort_order"):
        if name in given:
            value = getattr(body, name)
            if value is None and name in ("display_name", "visibility", "sort_order"):
                raise invalid(to_camel(name), "This value can't be empty.")
            v[name] = value.strip() if isinstance(value, str) else value
    if "folder_name" in given:
        if body.folder_name is None:
            raise invalid("folderName", "This value can't be empty.")
        v["folder_name"] = folder(body.folder_name)
    if "siren" in given:
        v["siren"] = siren(body.siren)
    if "fiscal_year_end" in given:
        if body.fiscal_year_end is None:
            raise invalid("fiscalYearEnd", "This value can't be empty.")
        v["fy_end_month"], v["fy_end_day"] = fy_end(body.fiscal_year_end)
    for name in ("aliases", "addresses"):
        if name in given and getattr(body, name) is not None:
            v[name] = [x.strip() for x in getattr(body, name) if x.strip()]
    return v


def _create_entity(body: EntityWrite) -> dict[str, Any]:
    given = body.model_fields_set
    if "purge_after_hours" in given:
        raise ApiFailure(403, "not_allowed", "Only the seed creates the Visitors entity.",
                         field="purgeAfterHours")  # fmt: skip
    values = _entity_values(body, given | {"fiscal_year_end", "folder_name"})
    eid = new_id("ent")
    try:
        with _tx() as conn:
            values.setdefault("key", free_key(conn, "entities", slugify(body.folder_name)))
            conn.execute(insert(T["entities"]).values(id=eid, **values))
            return entity_detail(conn, eid)
    except IntegrityError as err:
        raise _unique(err) from None


@router.post(
    "/entities", operation_id="createEntity", status_code=201, response_model=EntityDetail,
    responses=errors(400, 401, 403, 409, 415, 422, 423),
)  # fmt: skip
async def create_entity(body: EntityWrite) -> dict[str, Any]:
    return await run(_create_entity, body)


def _patch_entity(entity_id: str, body: EntityPatch) -> dict[str, Any]:
    given = set(body.model_fields_set)
    e = T["entities"]
    try:
        with _tx() as conn:
            row = conn.execute(select(e).where(e.c.id == entity_id)).mappings().first()
            if row is None:
                raise not_found("entity")
            visitors = row["purge_after_hours"] is not None
            if visitors and given - VISITORS_FIELDS:
                field = to_camel(sorted(given - VISITORS_FIELDS)[0])
                raise ApiFailure(403, "not_allowed", "The Visitors entity keeps its identity.",
                                 field=field)  # fmt: skip
            if not visitors and "purge_after_hours" in given:
                raise ApiFailure(403, "not_allowed", "Only the Visitors entity is purged.",
                                 field="purgeAfterHours")  # fmt: skip
            values = _entity_values(body, given)
            if visitors and "purge_after_hours" in given:
                hours = body.purge_after_hours
                if hours is None or not PURGE_HOURS[0] <= hours <= PURGE_HOURS[1]:
                    raise invalid("purgeAfterHours", "Use a whole number of hours from 1 to 168.")
                values["purge_after_hours"] = hours
            if values:
                conn.execute(
                    update(e).where(e.c.id == entity_id).values(**values, updated_at=clock.now())
                )
            return entity_detail(conn, entity_id)
    except IntegrityError as err:
        raise _unique(err) from None


@router.patch(
    "/entities/{id}", operation_id="patchEntity", response_model=EntityDetail,
    responses=errors(400, 401, 403, 404, 409, 415, 422, 423),
)  # fmt: skip
async def patch_entity(entity_id: EntityId, body: EntityPatch) -> dict[str, Any]:
    return await run(_patch_entity, entity_id, body)


def rules_naming(
    conn: Connection, *, entity: str | None = None, unit: tuple[str, str] | None = None,
    account: str | None = None,
) -> bool:  # fmt: skip
    """Whether any rule's action or conditions name this entity key, sub-unit or account key."""
    for conditions, action in conn.execute(select(T["rules"].c.conditions, T["rules"].c.action)):
        if entity is not None:
            if action.get("entity") == entity:
                return True
            for c in conditions:
                if c.get("field") in ("entity", "addressee", "iban", "siren"):
                    value = c.get("value")
                    if value == entity or (isinstance(value, list) and entity in value):
                        if c.get("op") in ("equals", "in", "is_entity", "entity"):
                            return True
        if unit is not None and action.get("entity") == unit[0] and action.get("unit") == unit[1]:
            return True
        if account is not None:
            if any(c.get("field") == "iban" and c.get("op") == "account"
                   and c.get("value") == account for c in conditions):  # fmt: skip
                return True
    return False


def _entity_references(conn: Connection, row: Any) -> list[str]:
    eid = row["id"]
    checks = {
        "documents": select(T["documents"].c.id).where(T["documents"].c.entity_id == eid),
        "classifications": select(T["classifications"].c.id).where(
            T["classifications"].c.entity_id == eid
        ),
        "deadlines": select(T["deadlines"].c.id).where(T["deadlines"].c.entity_id == eid),
        "sub_units": select(T["sub_units"].c.id).where(T["sub_units"].c.entity_id == eid),
        "accounts": select(T["accounts"].c.id).where(T["accounts"].c.entity_id == eid),
        "exports": select(T["exports"].c.id).where(T["exports"].c.entity_id == eid),
    }
    found = [kind for kind, q in checks.items() if conn.execute(exists(q).select()).scalar()]
    if rules_naming(conn, entity=row["key"]):
        found.append("rules")
    return found


def in_use(references: list[str]) -> ApiFailure:
    return ApiFailure(409, "in_use", "It is still in use.", details={"references": references})


def _delete_entity(entity_id: str) -> None:
    e = T["entities"]
    with _tx() as conn:
        row = (
            conn.execute(select(e).where(e.c.id == entity_id).with_for_update()).mappings().first()
        )
        if row is None:
            raise not_found("entity")
        if row["purge_after_hours"] is not None:
            raise ApiFailure(403, "not_allowed", "The Visitors entity can't be deleted.")
        refs = _entity_references(conn, row)
        if refs:
            raise in_use(refs)
        conn.execute(delete(e).where(e.c.id == entity_id))


@router.delete(
    "/entities/{id}", operation_id="deleteEntity", status_code=204,
    responses=errors(401, 403, 404, 409, 423),
)  # fmt: skip
async def delete_entity(entity_id: EntityId) -> Response:
    await run(_delete_entity, entity_id)
    return Response(status_code=204)


# --- sub-units ---


def _person_exists(conn: Connection, person_id: str | None, field: str) -> None:
    body_id(person_id, "per", field)
    p = T["people"]
    if person_id and conn.execute(select(p.c.id).where(p.c.id == person_id)).first() is None:
        raise ApiFailure(400, "invalid_request", "Unknown person.", field=field)


def _entity_row(conn: Connection, entity_id: str, *, editable: bool = True) -> Any:
    e = T["entities"]
    row = conn.execute(select(e).where(e.c.id == entity_id)).mappings().first()
    if row is None:
        raise not_found("entity")
    if editable and row["purge_after_hours"] is not None:
        raise ApiFailure(403, "not_allowed", "The Visitors entity keeps its identity.")
    return row


def _create_sub_unit(entity_id: str, body: SubUnitWrite) -> dict[str, Any]:
    check_key(body.key)
    try:
        with _tx() as conn:
            _entity_row(conn, entity_id)
            _person_exists(conn, body.person_id, "personId")
            key = body.key or free_key(conn, "sub_units", slugify(body.label), entity_id=entity_id)
            conn.execute(
                insert(T["sub_units"]).values(
                    id=new_id("sub"), entity_id=entity_id, key=key, label=folder_label(body.label),
                    person_id=body.person_id,
                )
            )  # fmt: skip
            return entity_detail(conn, entity_id)
    except IntegrityError as err:
        raise _unique(err) from None


def folder_label(value: str) -> str:
    if folder_segment(value) != value:
        raise invalid("label", "The label has characters a folder can't hold.")
    return value


@router.post(
    "/entities/{id}/sub-units", operation_id="createSubUnit", status_code=201,
    response_model=EntityDetail, responses=errors(400, 401, 403, 404, 409, 415, 422, 423),
)  # fmt: skip
async def create_sub_unit(entity_id: EntityId, body: SubUnitWrite) -> dict[str, Any]:
    return await run(_create_sub_unit, entity_id, body)


def _sub_unit(conn: Connection, sub_unit_id: str) -> Any:
    s = T["sub_units"]
    row = conn.execute(select(s).where(s.c.id == sub_unit_id)).mappings().first()
    if row is None:
        raise not_found("sub-unit")
    return row


def _patch_sub_unit(sub_unit_id: str, body: SubUnitPatch) -> dict[str, Any]:
    given = body.model_fields_set
    s = T["sub_units"]
    values: dict[str, Any] = {}
    if "key" in given:
        if body.key is None:
            raise invalid("key", "This value can't be empty.")
        check_key(body.key)
        values["key"] = body.key
    if "label" in given:
        if body.label is None:
            raise invalid("label", "This value can't be empty.")
        values["label"] = folder_label(body.label)
    try:
        with _tx() as conn:
            row = _sub_unit(conn, sub_unit_id)
            if "person_id" in given:
                _person_exists(conn, body.person_id, "personId")
                values["person_id"] = body.person_id
            if values:
                conn.execute(
                    update(s).where(s.c.id == sub_unit_id).values(**values, updated_at=clock.now())
                )
            return entity_detail(conn, row["entity_id"])
    except IntegrityError as err:
        raise _unique(err) from None


@router.patch(
    "/sub-units/{id}", operation_id="patchSubUnit", response_model=EntityDetail,
    responses=errors(400, 401, 404, 409, 415, 422, 423),
)  # fmt: skip
async def patch_sub_unit(sub_unit_id: SubUnitId, body: SubUnitPatch) -> dict[str, Any]:
    return await run(_patch_sub_unit, sub_unit_id, body)


def _delete_sub_unit(sub_unit_id: str) -> None:
    s, d, c, e = T["sub_units"], T["documents"], T["classifications"], T["entities"]
    with _tx() as conn:
        row = _sub_unit(conn, sub_unit_id)
        refs = []
        if conn.execute(
            exists(select(d.c.id).where(d.c.sub_unit_id == sub_unit_id)).select()
        ).scalar():
            refs.append("documents")
        if conn.execute(
            exists(select(c.c.id).where(c.c.sub_unit_id == sub_unit_id)).select()
        ).scalar():
            refs.append("classifications")
        entity_key = conn.execute(select(e.c.key).where(e.c.id == row["entity_id"])).scalar_one()
        if rules_naming(conn, unit=(entity_key, row["key"])):
            refs.append("rules")
        if refs:
            raise in_use(refs)
        conn.execute(delete(s).where(s.c.id == sub_unit_id))


@router.delete(
    "/sub-units/{id}", operation_id="deleteSubUnit", status_code=204,
    responses=errors(401, 404, 409, 423),
)  # fmt: skip
async def delete_sub_unit(sub_unit_id: SubUnitId) -> Response:
    await run(_delete_sub_unit, sub_unit_id)
    return Response(status_code=204)


# --- accounts (the IBAN is never stored, logged or echoed) ---


def _create_account(entity_id: str, body: AccountWrite) -> dict[str, Any]:
    check_key(body.key)
    if not is_valid_iban(body.iban):
        raise invalid("iban", "The IBAN's checksum or length is wrong.")
    normal = normalize_iban(body.iban)
    try:
        with _tx() as conn:
            _entity_row(conn, entity_id)
            body_id(body.sub_unit_id, "sub", "subUnitId")
            body_id(body.bank_counterparty_id, "cpt", "bankCounterpartyId")
            if body.sub_unit_id:
                s = T["sub_units"]
                owner = conn.execute(
                    select(s.c.entity_id).where(s.c.id == body.sub_unit_id)
                ).scalar()
                if owner != entity_id:
                    raise ApiFailure(400, "invalid_request", "Unknown sub-unit.", field="subUnitId")
            if body.bank_counterparty_id:
                cp = T["counterparties"]
                if (
                    conn.execute(
                        select(cp.c.id).where(cp.c.id == body.bank_counterparty_id)
                    ).first()
                    is None
                ):
                    raise ApiFailure(400, "invalid_request", "Unknown counterparty.",
                                     field="bankCounterpartyId")  # fmt: skip
            salt = bytes(conn.execute(select(T["settings"].c.iban_salt)).scalar_one())
            key = body.key or free_key(conn, "accounts", slugify(body.label))
            conn.execute(
                insert(T["accounts"]).values(
                    id=new_id("acc"), key=key, entity_id=entity_id, sub_unit_id=body.sub_unit_id,
                    bank_counterparty_id=body.bank_counterparty_id, label=body.label.strip(),
                    iban_hash=iban_hash(normal, salt), iban_last4=iban_last4(normal),
                    currency=body.currency,
                )
            )  # fmt: skip
            return entity_detail(conn, entity_id)
    except IntegrityError as err:
        raise _unique(err) from None


@router.post(
    "/entities/{id}/accounts", operation_id="createAccount", status_code=201,
    response_model=EntityDetail, responses=errors(400, 401, 403, 404, 409, 415, 422, 423),
)  # fmt: skip
async def create_account(entity_id: EntityId, body: AccountWrite) -> dict[str, Any]:
    return await run(_create_account, entity_id, body)


def _delete_account(account_id: str) -> None:
    a = T["accounts"]
    with _tx() as conn:
        row = conn.execute(select(a).where(a.c.id == account_id)).mappings().first()
        if row is None:
            raise not_found("account")
        if rules_naming(conn, account=row["key"]):
            raise in_use(["rules"])
        conn.execute(delete(a).where(a.c.id == account_id))


@router.delete(
    "/accounts/{id}", operation_id="deleteAccount", status_code=204,
    responses=errors(401, 404, 409, 423),
)  # fmt: skip
async def delete_account(account_id: AccountId) -> Response:
    await run(_delete_account, account_id)
    return Response(status_code=204)


# --- people ---


def person_detail(conn: Connection, person_id: str) -> dict[str, Any]:
    p = T["people"]
    row = conn.execute(select(p).where(p.c.id == person_id)).mappings().first()
    if row is None:
        raise not_found("person")
    return {
        "id": row["id"], "key": row["key"], "display_name": row["display_name"],
        "short_name": row["short_name"], "aliases": list(row["aliases"]),
    }  # fmt: skip


def _people() -> dict[str, Any]:
    p = T["people"]
    with _conn() as conn:
        ids = conn.execute(select(p.c.id).order_by(p.c.display_name, p.c.id)).scalars().all()
        return {"items": [person_detail(conn, i) for i in ids]}


@router.get(
    "/people", operation_id="listPeople", response_model=PersonList, responses=errors(401, 423)
)
async def list_people() -> dict[str, Any]:
    return await run(_people)


def _person_values(body: PersonWrite | PersonPatch, given: set[str]) -> dict[str, Any]:
    v: dict[str, Any] = {}
    if "key" in given:
        check_key(body.key)
        if body.key is not None:
            v["key"] = body.key
    if "display_name" in given:
        if body.display_name is None:
            raise invalid("displayName", "This value can't be empty.")
        v["display_name"] = body.display_name.strip()
    if "short_name" in given:
        v["short_name"] = body.short_name
    if "aliases" in given and body.aliases is not None:
        v["aliases"] = [x.strip() for x in body.aliases if x.strip()]
    return v


def _create_person(body: PersonWrite) -> dict[str, Any]:
    values = _person_values(body, body.model_fields_set | {"display_name"})
    pid = new_id("per")
    try:
        with _tx() as conn:
            values.setdefault("key", free_key(conn, "people", slugify(body.display_name)))
            conn.execute(insert(T["people"]).values(id=pid, **values))
            return person_detail(conn, pid)
    except IntegrityError as err:
        raise _unique(err) from None


@router.post(
    "/people", operation_id="createPerson", status_code=201, response_model=PersonDetail,
    responses=errors(400, 401, 403, 409, 415, 422, 423),
)  # fmt: skip
async def create_person(body: PersonWrite) -> dict[str, Any]:
    return await run(_create_person, body)


def _patch_person(person_id: str, body: PersonPatch) -> dict[str, Any]:
    values = _person_values(body, set(body.model_fields_set))
    p = T["people"]
    try:
        with _tx() as conn:
            person_detail(conn, person_id)
            if values:
                conn.execute(
                    update(p).where(p.c.id == person_id).values(**values, updated_at=clock.now())
                )
            return person_detail(conn, person_id)
    except IntegrityError as err:
        raise _unique(err) from None


@router.patch(
    "/people/{id}", operation_id="patchPerson", response_model=PersonDetail,
    responses=errors(400, 401, 404, 409, 415, 422, 423),
)  # fmt: skip
async def patch_person(person_id: PersonId, body: PersonPatch) -> dict[str, Any]:
    return await run(_patch_person, person_id, body)


def _link(entity_id: str, person_id: str, body: EntityPersonWrite | None) -> dict[str, Any]:
    ep = T["entity_people"]
    with _tx() as conn:
        _entity_row(conn, entity_id)
        person_detail(conn, person_id)
        role = body.role if body else None
        conn.execute(
            pg_insert(ep)
            .values(entity_id=entity_id, person_id=person_id, role=role)
            .on_conflict_do_update(index_elements=["entity_id", "person_id"], set_={"role": role})
        )
        return entity_detail(conn, entity_id)


def _unlink(entity_id: str, person_id: str) -> dict[str, Any]:
    ep = T["entity_people"]
    with _tx() as conn:
        _entity_row(conn, entity_id)
        conn.execute(delete(ep).where(ep.c.entity_id == entity_id, ep.c.person_id == person_id))
        return entity_detail(conn, entity_id)


@router.put(
    "/entities/{id}/people/{personId}", operation_id="linkEntityPerson",
    response_model=EntityDetail, responses=errors(400, 401, 403, 404, 415, 423),
)  # fmt: skip
async def link_person(
    entity_id: EntityId, person_id: PersonPathId, body: EntityPersonWrite | None = None
) -> dict[str, Any]:
    return await run(_link, entity_id, person_id, body)


@router.delete(
    "/entities/{id}/people/{personId}", operation_id="unlinkEntityPerson",
    response_model=EntityDetail, responses=errors(401, 403, 404, 423),
)  # fmt: skip
async def unlink_person(entity_id: EntityId, person_id: PersonPathId) -> dict[str, Any]:
    return await run(_unlink, entity_id, person_id)


# --- categories and templates ---


def category_dto(conn: Connection, category_id: str) -> dict[str, Any]:
    c, sc, t = T["categories"], T["subcategories"], T["templates"]
    row = conn.execute(select(c).where(c.c.id == category_id)).mappings().first()
    if row is None:
        raise not_found("category")
    subs = conn.execute(
        select(sc).where(sc.c.category_id == category_id).order_by(sc.c.sort_order, sc.c.key)
    ).mappings()
    tpls = conn.execute(select(t).where(t.c.category_id == category_id)).mappings().all()
    default = next((x for x in tpls if x["entity_id"] is None), None)
    return Category(
        id=row["id"],
        labels=row["labels"],
        icon=row["icon"],
        subcategories=[{"key": x["key"], "labels": x["labels"]} for x in subs],
        template={
            "path_template": default["path_template"] if default else "",
            "file_template": default["file_template"] if default else "",
        },
        entity_templates=[
            {
                "entity_id": x["entity_id"],
                "path_template": x["path_template"],
                "file_template": x["file_template"],
            }
            for x in sorted(tpls, key=lambda x: x["entity_id"] or "")
            if x["entity_id"] is not None
        ],  # fmt: skip
    ).model_dump(mode="json", by_alias=False)


def _categories() -> dict[str, Any]:
    c, d = T["categories"], T["documents"]
    with _conn() as conn:
        ids = conn.execute(select(c.c.id).order_by(c.c.sort_order, c.c.id)).scalars().all()
        counts = dict(
            conn.execute(
                select(d.c.category_id, func.count())
                .where(d.c.deleted_at.is_(None), d.c.category_id.is_not(None))
                .group_by(d.c.category_id)
            ).all()
        )
        return {
            "items": [category_dto(conn, i) for i in ids],
            "document_counts": {i: counts.get(i, 0) for i in ids},
        }


@router.get(
    "/categories", operation_id="listCategories", response_model=CategoryList,
    responses=errors(401, 423),
)  # fmt: skip
async def list_categories() -> dict[str, Any]:
    return await run(_categories)


def check_icon(icon: str) -> str:
    if icon not in ICONS:
        raise invalid("icon", "Use one of the design system's category icons.")
    return icon


def _create_category(body: CategoryWrite) -> dict[str, Any]:
    if not CATEGORY_ID.match(body.id):
        raise invalid("id", "Use a slug: a-z, 0-9 and '_', starting with a letter, 2-40 long.")
    labels = check_labels(body.labels)
    check_icon(body.icon)
    check_templates(body.template.path_template, body.template.file_template)
    c = T["categories"]
    try:
        with _tx() as conn:
            order = conn.execute(select(func.coalesce(func.max(c.c.sort_order), 0))).scalar_one()
            conn.execute(
                insert(c).values(
                    id=body.id, labels=labels, icon=body.icon,
                    model_definition=body.model_definition.strip(), sort_order=order + 10,
                )
            )  # fmt: skip
            conn.execute(
                insert(T["templates"]).values(
                    id=new_id("tpl"), category_id=body.id, entity_id=None,
                    path_template=body.template.path_template,
                    file_template=body.template.file_template,
                )
            )  # fmt: skip
            return category_dto(conn, body.id)
    except IntegrityError as err:
        raise _unique(err) from None


@router.post(
    "/categories", operation_id="createCategory", status_code=201, response_model=Category,
    responses=errors(400, 401, 403, 409, 415, 422, 423),
)  # fmt: skip
async def create_category(body: CategoryWrite) -> dict[str, Any]:
    return await run(_create_category, body)


def _category_exists(conn: Connection, category_id: str) -> None:
    c = T["categories"]
    if conn.execute(select(c.c.id).where(c.c.id == category_id)).first() is None:
        raise not_found("category")


def _patch_category(category_id: str, body: CategoryPatch) -> dict[str, Any]:
    given = body.model_fields_set
    values: dict[str, Any] = {}
    for name in given:
        if getattr(body, name) is None:
            raise invalid(to_camel(name), "This value can't be empty.")
    if "labels" in given:
        values["labels"] = check_labels(body.labels)  # type: ignore[arg-type]
    if "icon" in given:
        values["icon"] = check_icon(body.icon)  # type: ignore[arg-type]
    if "model_definition" in given:
        values["model_definition"] = body.model_definition.strip()  # type: ignore[union-attr]
    if body.template is not None:
        check_templates(body.template.path_template, body.template.file_template)
    c, t = T["categories"], T["templates"]
    now = clock.now()
    with _tx() as conn:
        _category_exists(conn, category_id)
        if values:
            conn.execute(update(c).where(c.c.id == category_id).values(**values, updated_at=now))
        if body.template is not None:
            conn.execute(
                update(t)
                .where(t.c.category_id == category_id, t.c.entity_id.is_(None))
                .values(
                    path_template=body.template.path_template,
                    file_template=body.template.file_template, updated_at=now,
                )
            )  # fmt: skip
        return category_dto(conn, category_id)


@router.patch(
    "/categories/{id}", operation_id="patchCategory", response_model=Category,
    responses=errors(400, 401, 404, 415, 422, 423),
)  # fmt: skip
async def patch_category(id: str, body: CategoryPatch) -> dict[str, Any]:  # noqa: A002
    return await run(_patch_category, id, body)


def _put_template(category_id: str, entity_id: str, body: TemplatePair) -> dict[str, Any]:
    check_templates(body.path_template, body.file_template)
    t = T["templates"]
    now = clock.now()
    with _tx() as conn:
        _category_exists(conn, category_id)
        _entity_row(conn, entity_id, editable=False)
        found = conn.execute(
            select(t.c.id).where(t.c.category_id == category_id, t.c.entity_id == entity_id)
        ).scalar()
        if found:
            conn.execute(
                update(t).where(t.c.id == found).values(
                    path_template=body.path_template, file_template=body.file_template,
                    updated_at=now,
                )
            )  # fmt: skip
        else:
            conn.execute(
                insert(t).values(
                    id=new_id("tpl"), category_id=category_id, entity_id=entity_id,
                    path_template=body.path_template, file_template=body.file_template,
                )
            )  # fmt: skip
        return category_dto(conn, category_id)


@router.put(
    "/categories/{id}/templates/{entityId}", operation_id="putEntityTemplate",
    response_model=Category, responses=errors(400, 401, 404, 415, 422, 423),
)  # fmt: skip
async def put_template(
    id: str,  # noqa: A002
    entity_id: EntityPathId,
    body: TemplatePair,
) -> dict[str, Any]:
    return await run(_put_template, id, entity_id, body)


def _delete_template(category_id: str, entity_id: str) -> dict[str, Any]:
    t = T["templates"]
    with _tx() as conn:
        _category_exists(conn, category_id)
        conn.execute(delete(t).where(t.c.category_id == category_id, t.c.entity_id == entity_id))
        return category_dto(conn, category_id)


@router.delete(
    "/categories/{id}/templates/{entityId}", operation_id="deleteEntityTemplate",
    response_model=Category, responses=errors(401, 404, 423),
)  # fmt: skip
async def delete_template(id: str, entity_id: EntityPathId) -> dict[str, Any]:  # noqa: A002
    return await run(_delete_template, id, entity_id)


def _create_subcategory(category_id: str, body: SubcategoryWrite) -> dict[str, Any]:
    labels = check_labels(body.labels)
    if body.key is not None and not SUBCATEGORY_KEY.match(body.key):
        raise invalid("key", "Use a slug: a-z, 0-9 and '_', starting with a letter.")
    sc = T["subcategories"]
    try:
        with _tx() as conn:
            _category_exists(conn, category_id)
            taken = set(
                conn.execute(select(sc.c.key).where(sc.c.category_id == category_id)).scalars()
            )
            key = body.key
            if key is None:
                base, n = slugify(labels["en"], sep="_"), 2
                key = base
                while key in taken:
                    key, n = f"{base[:36]}_{n}", n + 1
            order = conn.execute(
                select(func.coalesce(func.max(sc.c.sort_order), 0)).where(
                    sc.c.category_id == category_id
                )
            ).scalar_one()
            conn.execute(
                insert(sc).values(
                    category_id=category_id, key=key, labels=labels, sort_order=order + 10
                )
            )
            return category_dto(conn, category_id)
    except IntegrityError as err:
        raise duplicate("key") from err


@router.post(
    "/categories/{id}/subcategories", operation_id="createSubcategory", status_code=201,
    response_model=Category, responses=errors(400, 401, 404, 409, 415, 422, 423),
)  # fmt: skip
async def create_subcategory(id: str, body: SubcategoryWrite) -> dict[str, Any]:  # noqa: A002
    return await run(_create_subcategory, id, body)


def _patch_subcategory(category_id: str, key: str, body: SubcategoryPatch) -> dict[str, Any]:
    labels = check_labels(body.labels)
    sc = T["subcategories"]
    with _tx() as conn:
        _category_exists(conn, category_id)
        res = conn.execute(
            update(sc).where(sc.c.category_id == category_id, sc.c.key == key).values(labels=labels)
        )
        if res.rowcount == 0:
            raise not_found("subcategory")
        return category_dto(conn, category_id)


@router.patch(
    "/categories/{id}/subcategories/{key}", operation_id="patchSubcategory",
    response_model=Category, responses=errors(400, 401, 404, 415, 422, 423),
)  # fmt: skip
async def patch_subcategory(id: str, key: str, body: SubcategoryPatch) -> dict[str, Any]:  # noqa: A002
    return await run(_patch_subcategory, id, key, body)


# --- template preview ---


def _preview(body: TemplatePreviewRequest) -> dict[str, Any]:
    for kind, template in (("path", body.path_template), ("file", body.file_template)):
        try:
            parse(template, kind)  # type: ignore[arg-type]
        except TemplateError as e:
            error = {"template": kind, "offset": e.offset, "message": e.message}
            return {"path": [], "file_name": None, "error": error}
    body_id(body.document_id, "doc", "documentId")
    body_id(body.entity_id, "ent", "entityId")
    with _conn() as conn:
        snap = reg.load(conn)
        values = _document_values(conn, snap, body.document_id) if body.document_id else None
        if values is None:
            values = _sample_values(snap, body.entity_id)
    try:
        rendered = render(body.path_template, body.file_template, values)
    except NotRenderable:
        return {"path": [], "file_name": None, "error": None}
    return {"path": list(rendered.folders), "file_name": rendered.file_name, "error": None}


def _document_values(conn: Connection, snap: Any, document_id: str) -> RenderValues:
    d = T["documents"]
    doc = conn.execute(
        select(d).where(d.c.id == document_id, d.c.deleted_at.is_(None))
    ).mappings().first()  # fmt: skip
    if doc is None:
        raise ApiFailure(400, "invalid_request", "Unknown document.", field="documentId")
    entity = snap.entity_keys.get(doc["entity_id"])
    unit = snap.sub_unit_keys.get(doc["sub_unit_id"], (None, None))[1]
    return render_values(
        snap, doc, entity=entity, unit=unit, category=doc["category_id"],
        subcategory=doc["subcategory_key"],
        counterparty=snap.counterparty_keys.get(doc["counterparty_id"]),
    )  # fmt: skip


def _sample_values(snap: Any, entity_id: str | None) -> RenderValues:
    e = None
    if entity_id is not None:
        key = snap.entity_keys.get(entity_id)
        if key is None:
            raise ApiFailure(400, "invalid_request", "Unknown entity.", field="entityId")
        e = snap.entities[key]
    else:
        practice = [
            x for x in snap.entities.values()
            if x["visibility"] == "practice" and x["purge_after_hours"] is None
        ]  # fmt: skip
        e = min(practice, key=lambda x: (x["sort_order"], x["key"]), default=None)
    info = (
        EntityInfo(e["key"], e["folder_name"], e["fy_end_month"], e["fy_end_day"],
                   e["filing_language"])
        if e else None
    )  # fmt: skip
    return RenderValues(
        entity=info, arrived_at=SAMPLE["arrived_at"],
        language=snap.lang_for(e["key"]) if e else snap.language,
        category_labels=SAMPLE["category"], subcategory_labels=SAMPLE["subcategory"],
        counterparty=SAMPLE["counterparty"], reference=SAMPLE["reference"],
        doc_date=SAMPLE["doc_date"], period_end=SAMPLE["period_end"],
    )  # fmt: skip


@router.post(
    "/templates/preview", operation_id="previewTemplate", response_model=TemplatePreview,
    responses=errors(400, 401, 403, 415, 423),
)  # fmt: skip
async def preview_template(body: TemplatePreviewRequest) -> dict[str, Any]:
    return await run(_preview, body)


# --- counterparties ---


def _counterparties(q: str | None, limit: int) -> list[dict[str, Any]]:
    cp, al = T["counterparties"], T["counterparty_aliases"]
    with _conn() as conn:
        if not q or not norm(q):
            rows = conn.execute(
                select(cp.c.id, cp.c.key, cp.c.name, cp.c.kind).order_by(cp.c.name).limit(limit)
            ).all()
        else:
            wanted = norm(q)
            score = func.max(
                func.greatest(
                    func.similarity(al.c.alias_norm, wanted),
                    func.word_similarity(wanted, al.c.alias_norm),
                )
            )
            rows = conn.execute(
                select(cp.c.id, cp.c.key, cp.c.name, cp.c.kind)
                .join(al, al.c.counterparty_id == cp.c.id)
                .where(
                    or_(
                        al.c.alias_norm.contains(wanted, autoescape=True),
                        func.similarity(al.c.alias_norm, wanted) >= TRIGRAM_MIN,
                        func.word_similarity(wanted, al.c.alias_norm) >= TRIGRAM_MIN,
                    )
                )
                .group_by(cp.c.id, cp.c.key, cp.c.name, cp.c.kind)
                .order_by(score.desc(), cp.c.name)
                .limit(limit)
            ).all()
    return [
        Counterparty(id=r.id, key=r.key, name=r.name, kind=r.kind).model_dump(by_alias=False)
        for r in rows
    ]


@router.get(
    "/counterparties", operation_id="listCounterparties", response_model=list[Counterparty],
    responses=errors(400, 401, 423),
)  # fmt: skip
async def counterparties(
    q: Annotated[str | None, Query(max_length=160)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = COUNTERPARTY_LIMIT,
) -> list[dict[str, Any]]:
    return await run(_counterparties, q, limit)
