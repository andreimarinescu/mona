import json
import secrets

import psycopg
import pytest
from psycopg import errors

from mona.ids import new_id
from mona.settings import get_settings


@pytest.fixture
def db():
    with psycopg.connect(get_settings().libpq_url) as conn:
        conn.execute("BEGIN")
        yield conn
        conn.rollback()


def fails(conn, sql, params=(), error=errors.IntegrityError):
    conn.execute("SAVEPOINT s")
    with pytest.raises(error):
        conn.execute(sql, params)
    conn.execute("ROLLBACK TO SAVEPOINT s")


def entity(conn, **cols):
    cols = {"id": new_id("ent"), "key": new_id("k")[-10:], "display_name": "E", **cols}
    cols.setdefault("folder_name", cols["key"])
    names = ", ".join(cols)
    conn.execute(
        f"INSERT INTO entities ({names}) VALUES ({', '.join(['%s'] * len(cols))})",
        list(cols.values()),
    )
    return cols["id"]


def batch(conn):
    bid = new_id("bat")
    conn.execute("INSERT INTO batches (id, source) VALUES (%s, 'drop')", (bid,))
    return bid


DOC_SQL = (
    "INSERT INTO documents (id, sha256, original_name, mime_type, size_bytes, source, batch_id,"
    " location, current_path, status, amount, currency, reasons)"
    " VALUES (%s, %s, 'x.pdf', 'application/pdf', 1, 'drop', %s, %s, %s, %s, %s, %s, %s)"
)


def document(
    conn,
    bid,
    *,
    location="inbox",
    status="processing",
    amount=None,
    currency=None,
    reasons=(),
    sha=None,
):
    did = new_id("doc")
    conn.execute(
        DOC_SQL,
        (
            did,
            sha or secrets.token_hex(32),
            bid,
            location,
            f"{did}.pdf",
            status,
            amount,
            currency,
            list(reasons),
        ),
    )
    return did


def file_op(conn, action="file", undo_of=None, fs_state="done"):
    return conn.execute(
        "INSERT INTO file_ops (actor, via, action, undoable, undo_of, fs_state)"
        " VALUES ('user', 'ui', %s, true, %s, %s) RETURNING id",
        (action, undo_of, fs_state),
    ).fetchone()[0]


def test_bad_id_prefix(db):
    fails(
        db,
        "INSERT INTO entities (id, key, display_name, folder_name) VALUES (%s, 'k', 'E', 'F')",
        (new_id("doc"),),
        errors.CheckViolation,
    )
    fails(
        db,
        "INSERT INTO entities (id, key, display_name, folder_name) VALUES"
        " ('ent_notaulid', 'k', 'E', 'F')",
        (),
        errors.CheckViolation,
    )


def test_document_constraints(db):
    bid = batch(db)
    document(db, bid, amount=10, currency="EUR")
    fails(
        db,
        DOC_SQL,
        (new_id("doc"), "b" * 64, bid, "inbox", "p1", "processing", 10, None, []),
        errors.CheckViolation,
    )
    fails(
        db,
        DOC_SQL,
        (new_id("doc"), "c" * 64, bid, "inbox", "p2", "filed", None, None, []),
        errors.CheckViolation,
    )
    fails(
        db,
        DOC_SQL,
        (new_id("doc"), "d" * 64, bid, "inbox", "p3", "review", None, None, ["odd"]),
        errors.CheckViolation,
    )


def test_fiscal_year_end_day(db):
    entity(db, fy_end_month=6, fy_end_day=30)
    fails(
        db,
        "INSERT INTO entities (id, key, display_name, folder_name, fy_end_month, fy_end_day)"
        " VALUES (%s, 'apr', 'E', 'apr', 4, 31)",
        (new_id("ent"),),
        errors.CheckViolation,
    )


def test_one_open_review_item(db):
    did = document(db, batch(db), status="review", reasons=["low"], sha="e" * 64)
    sql = "INSERT INTO review_items (id, document_id, reasons) VALUES (%s, %s, '{low}')"
    db.execute(sql, (new_id("rev"), did))
    fails(db, sql, (new_id("rev"), did), errors.UniqueViolation)


def test_one_open_chat_turn(db):
    cid = new_id("cnv")
    db.execute("INSERT INTO conversations (id, title) VALUES (%s, 't')", (cid,))
    sql = (
        "INSERT INTO chat_turns (id, conversation_id, user_text, ui_message_id, reply_language,"
        " lease_expires_at) VALUES (%s, %s, 'hi', 'm', 'en', now())"
    )
    db.execute(sql, (new_id("trn"), cid))
    fails(db, sql, (new_id("trn"), cid), errors.UniqueViolation)


def test_settings_thresholds(db):
    fails(
        db,
        "INSERT INTO settings (practice_name, iban_salt, confidence_low, confidence_high)"
        " VALUES ('P', '\\x00', 85, 85)",
        (),
        errors.CheckViolation,
    )


def test_category_icon_and_labels(db):
    labels = json.dumps({"en": "a", "fr": "b", "ro": "c"})
    sql = "INSERT INTO categories (id, labels, icon, model_definition) VALUES (%s, %s, %s, 'd')"
    db.execute(sql, ("bank", labels, "bank"))
    fails(db, sql, ("odd", labels, "rocket"), errors.CheckViolation)
    fails(db, sql, ("no_ro", json.dumps({"en": "a", "fr": "b"}), "bank"), errors.CheckViolation)


def test_undo_requires_undo_of(db):
    fails(
        db,
        "INSERT INTO file_ops (actor, via, action, undoable) VALUES ('user', 'ui', 'undo', true)",
        (),
        errors.CheckViolation,
    )


def test_one_intake_group_per_batch(db):
    bid = batch(db)
    sql = (
        "INSERT INTO op_groups (id, kind, actor, via, batch_id)"
        " VALUES (%s, 'intake_batch', 'mona', 'pipeline', %s)"
    )
    db.execute(sql, (new_id("grp"), bid))
    fails(db, sql, (new_id("grp"), bid), errors.UniqueViolation)


def test_one_visitors_entity(db):
    entity(db, purge_after_hours=24)
    fails(
        db,
        "INSERT INTO entities (id, key, display_name, folder_name, purge_after_hours)"
        " VALUES (%s, 'v2', 'V2', 'V2', 48)",
        (new_id("ent"),),
        errors.UniqueViolation,
    )


def test_one_live_undo_per_entry(db):
    target = file_op(db)
    file_op(db, "undo", undo_of=target)
    fails(
        db,
        "INSERT INTO file_ops (actor, via, action, undoable, undo_of)"
        " VALUES ('user', 'ui', 'undo', true, %s)",
        (target,),
        errors.UniqueViolation,
    )


def test_undo_after_failed_undo_succeeds(db):
    target = file_op(db)
    file_op(db, "undo", undo_of=target, fs_state="failed")
    file_op(db, "undo", undo_of=target)
