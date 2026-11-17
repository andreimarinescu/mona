import json

from mona.pipeline import schema as output_schema


def test_model_schema_has_no_shorthand_classes():
    # A41: llama.cpp's grammar builder rejects \d (FIX-15)
    built = output_schema.build(["admin"], ["admin.urssaf"], ["cabinet"])
    assert "\\d" not in json.dumps(built)


def test_date_pattern_accepts_iso_only():
    assert output_schema.errors("2026-10-23", output_schema.DATE) == []
    assert output_schema.errors("23/10/2026", output_schema.DATE)
    assert output_schema.errors("2026-1-23", output_schema.DATE)
