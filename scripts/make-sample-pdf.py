# /// script
# requires-python = ">=3.12"
# dependencies = ["reportlab==5.0.1"]
# ///
"""Render the synthetic URSSAF-style payment demand used by /dev/pdf. Everything in it is fictional."""

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "apps/web/public/dev/sample.pdf"

LINES = [
    ("Helvetica-Bold", 16, "Union de recouvrement fictive — URSSAF (exemple)"),
    ("Helvetica", 10, "Document fictif de démonstration, sans valeur."),
    ("Helvetica", 11, ""),
    ("Helvetica", 11, "Cabinet dentaire Exemple"),
    ("Helvetica", 11, "12 rue des Oliviers, 00000 Villefictive"),
    ("Helvetica", 11, "N° de compte cotisant : 000-FICTIF-0000"),
    ("Helvetica", 11, ""),
    ("Helvetica-Bold", 13, "Appel de cotisations — 3e trimestre 2026"),
    ("Helvetica", 11, "Madame, Monsieur,"),
    ("Helvetica", 11, "Nous vous informons du montant de vos cotisations pour la période"),
    ("Helvetica", 11, "du 1er juillet 2026 au 30 septembre 2026."),
    ("Helvetica", 11, ""),
    ("Helvetica-Bold", 12, "Montant à payer : 1 284,00 €"),
    ("Helvetica-Bold", 12, "Date limite de paiement : 15 octobre 2026"),
    ("Helvetica", 11, ""),
    ("Helvetica", 11, "Paiement par prélèvement ou virement, référence 2026-T3-EXEMPLE."),
    ("Helvetica", 11, "En l’absence de paiement à l’échéance, des majorations de retard s’appliquent."),
]


def main(out: Path = OUT) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=A4, invariant=1)
    c.setTitle("Appel de cotisations (exemple fictif)")
    y = A4[1] - 25 * mm
    for font, size, text in LINES:
        c.setFont(font, size)
        c.drawString(20 * mm, y, text)
        y -= size * 1.6
    c.showPage()
    c.save()
    print(f"wrote {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
