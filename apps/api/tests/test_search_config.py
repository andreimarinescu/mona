import psycopg
import pytest

from mona.settings import get_settings
from mona.text import norm

TITLE = "Societatea \u0218tiin\u021bific\u0103 \u00b7 \u00c9ch\u00e9ance"


@pytest.mark.parametrize(
    "query",
    ["stiintifica", "\u015ftiin\u0163ific\u0103", "\u0219tiin\u021bific\u0103", "echeance"],
)
def test_mona_config_folds_accents_and_romanian_forms(query):
    with psycopg.connect(get_settings().libpq_url) as conn:
        hit = conn.execute(
            "SELECT to_tsvector('mona', %s) @@ websearch_to_tsquery('mona', %s)",
            (norm(TITLE), norm(query)),
        ).fetchone()[0]
    assert hit


def test_unaccent_is_the_second_line_of_defence():
    with psycopg.connect(get_settings().libpq_url) as conn:
        hit = conn.execute(
            "SELECT to_tsvector('mona', %s) @@ websearch_to_tsquery('mona', %s)",
            ("\u00c9ch\u00e9ance", "echeance"),
        ).fetchone()[0]
    assert hit
