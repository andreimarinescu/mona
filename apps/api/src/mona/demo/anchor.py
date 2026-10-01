"""C9 §6.4 re-anchoring: event timestamps move by Δ, printed dates never do."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import Connection, text

from mona.clock import PARIS
from mona.demo.tools import OpsError
from mona.fileops.state import iso, parse_ts

LEAD = timedelta(minutes=5)
JSON_TIMESTAMPS = (("file_ops", ("before", "after"), "filed_at"),)


def target_instant(anchor: date | None, now: datetime) -> datetime:
    """T1: 07:00 Europe/Paris on the anchor day, at most `now − 5 min`; a future day is refused."""
    today = now.astimezone(PARIS).date()
    day = anchor or today
    if day > today:
        raise OpsError(f"the anchor {day.isoformat()} is after today")
    t1 = datetime.combine(day, time(7, 0), tzinfo=PARIS)
    return min(t1, now - LEAD)


def shift_seconds(t0: datetime, t1: datetime) -> int:
    return int((t1 - t0).total_seconds())


def timestamp_columns(conn: Connection) -> dict[str, list[str]]:
    rows = conn.execute(
        text(
            "SELECT c.table_name, c.column_name FROM information_schema.columns c"
            " JOIN information_schema.tables t"
            " ON t.table_schema = c.table_schema AND t.table_name = c.table_name"
            " WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'"
            " AND c.data_type = 'timestamp with time zone'"
            " ORDER BY c.table_name, c.ordinal_position"
        )
    )
    out: dict[str, list[str]] = {}
    for table, column in rows:
        out.setdefault(table, []).append(column)
    return out


def reanchor(conn: Connection, delta_s: int) -> dict[str, int]:
    """Shift every timestamptz column and the PathState `filed_at`s by `delta_s` seconds, in the
    caller's transaction; `profile.locked_at` becomes null. Returns rows touched per table."""
    touched: dict[str, int] = {}
    delta = timedelta(seconds=delta_s)
    for table, columns in timestamp_columns(conn).items():
        sets = ", ".join(f'"{c}" = "{c}" + :d' for c in columns)
        touched[table] = conn.execute(text(f'UPDATE "{table}" SET {sets}'), {"d": delta}).rowcount
    for table, columns, key in JSON_TIMESTAMPS:
        for column in columns:
            rows = conn.execute(
                text(
                    f'SELECT id, "{column}"->>:k FROM "{table}" WHERE "{column}"->>:k IS NOT NULL'
                ),
                {"k": key},
            ).all()
            for row_id, value in rows:
                shifted = iso(parse_ts(value) + delta)  # type: ignore[operator]
                conn.execute(
                    text(
                        f'UPDATE "{table}" SET "{column}" = jsonb_set("{column}", :path,'
                        " to_jsonb(CAST(:v AS text))) WHERE id = :id"
                    ),
                    {"path": [key], "v": shifted, "id": row_id},
                )
    conn.execute(text("UPDATE profile SET locked_at = NULL"))
    return touched
