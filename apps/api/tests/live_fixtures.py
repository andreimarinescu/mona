"""Fictional filed documents for the live chat e2e; dev stack only.

Run in the api container: `python -m tests.live_fixtures` (replaces earlier fixture rows).
"""

import json
import sys
from datetime import date, timedelta

from mona import clock
from mona.settings import get_settings
from tests import rows
from tests.rows import CLEANUP


def main() -> None:
    if get_settings().mona_env != "dev":
        sys.exit("refusing: MONA_ENV is not dev")
    with rows.connect() as conn:
        for stmt in CLEANUP:
            conn.execute(stmt)
    today = clock.paris_today()
    last_year = today.year - 1
    d = rows.document
    ids = {
        "agipi_a": d(
            "AGIPI PER avis d'échéance avril",
            entity="personal",
            category="insurance",
            counterparty="agipi",
            doc_date=date(last_year, 4, 14),
            amount=520.0,
        ),
        "agipi_b": d(
            "AGIPI PER avis d'échéance octobre",
            entity="personal",
            category="insurance",
            counterparty="agipi",
            doc_date=date(last_year, 10, 14),
            amount=480.0,
        ),
        "agipi_older": d(
            "AGIPI PER avis d'échéance",
            entity="personal",
            category="insurance",
            counterparty="agipi",
            doc_date=date(last_year - 1, 4, 14),
            amount=450.0,
        ),
        "urssaf": d(
            "Appel de cotisation URSSAF 3e trimestre",
            entity="cabinet",
            category="payment_calls",
            doc_date=today - timedelta(days=20),
            amount=1284.0,
            due_date=today,
            text="Appel de cotisations sociales du 3e trimestre. Montant à payer 1 284,00 "
            "euros, à régler au plus tard à l'échéance. Cabinet Marchand SELARL.",
        ),
        "opco": d(
            "OPCO EP appel de contribution",
            entity="cabinet",
            category="payment_calls",
            counterparty="opco",
            doc_date=today - timedelta(days=40),
            amount=300.0,
            due_date=today - timedelta(days=5),
        ),
    }
    ids["ddl_urssaf"] = rows.deadline(
        "URSSAF 3e trimestre", today, amount=1284.0, document_id=ids["urssaf"]
    )
    ids["ddl_opco"] = rows.deadline(
        "OPCO EP contribution", today - timedelta(days=5), amount=300.0, document_id=ids["opco"]
    )
    ids["ddl_studio"] = rows.deadline(
        "TVA Studio Numérique", today + timedelta(days=20), entity="studio", amount=640.0
    )
    print(json.dumps({**ids, "today": today.isoformat(), "agipi_last_year_total": 1000.0}))


if __name__ == "__main__":
    main()
