"""C5 §10 `rules.yaml` export (the same schema the loader reads)."""

from datetime import UTC, datetime
from typing import Any

import yaml
from sqlalchemy import Connection, func, select

from mona.db.models import Rule, RuleVersion


def _ts(value: datetime | None) -> str | None:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


def export_rules(conn: Connection, *, now: datetime | None = None) -> dict[str, Any]:
    """Every rule, priority descending then key; `revision` counts rule_versions rows."""
    revision = conn.execute(select(func.count()).select_from(RuleVersion)).scalar_one()
    rows = conn.execute(select(Rule.__table__).order_by(Rule.priority.desc(), Rule.key)).mappings()
    return {
        "schema": "mona.rules/v1",
        "revision": revision,
        "exported_at": _ts(now or datetime.now(UTC)),
        "rules": [
            {
                "key": r["key"],
                "name": r["name"],
                "state": r["state"],
                "source": r["source"],
                "priority": r["priority"],
                "conditions": r["conditions"],
                "action": r["action"],
                "version": r["version"],
                "condition_text": r["condition_text"],
                "stats": {
                    "fired_count": r["fired_count"],
                    "last_fired_at": _ts(r["last_fired_at"]),
                    "corrections_since": r["corrections_since"],
                },
            }
            for r in rows
        ],
    }


def dump_rules_yaml(doc: dict[str, Any]) -> str:
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False)
