#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["reportlab", "pillow", "pyyaml", "numpy"]
# ///
"""Render the synthetic gap-filler documents from docs.yaml into the private demo-data directory."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEMO_DATA = Path.home() / "DevFiles" / "mona-hq" / "demo-data"
SEED = HERE.parent / "seed" / "practice.yaml"


def fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def fmt_amount(value: float) -> str:
    whole, cents = f"{abs(value):.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return ("-" if value < 0 else "") + " ".join(groups) + "," + cents + " €"


def resolve_date(spec: dict, anchor: date) -> date:
    if "offset" in spec:
        return anchor + timedelta(days=spec["offset"])
    dy, month, day = spec["ym"]
    return date(anchor.year + dy, month, day)


def rng_for(doc_id: str) -> np.random.Generator:
    return np.random.default_rng(int(hashlib.sha256(doc_id.encode()).hexdigest()[:8], 16))


def fake_digits(key: str, n: int) -> str:
    digest = hashlib.sha256(key.encode()).hexdigest()
    return "".join(str(int(c, 16) % 10) for c in digest)[:n]


def fake_iban(key: str) -> str:
    bban = fake_digits("iban:" + key, 23)
    check = 98 - int(bban + "152700", 10) % 97
    digits = f"{check:02d}" + bban
    return "FR" + digits[:2] + "".join(digits[i : i + 4] for i in range(2, 22, 4)) + digits[22:]


def fake_siren(key: str) -> str:
    d = fake_digits("siren:" + key, 9)
    return f"{d[:3]} {d[3:6]} {d[6:]}"


def check_text(text: str) -> str:
    text.encode("cp1252")
    return text


def esc(text: str) -> str:
    return check_text(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Ctx:
    def __init__(self, anchor: date, practice: dict):
        self.anchor = anchor
        self.people = {p["key"]: p["display_name"] for p in practice["people"] if isinstance(p["display_name"], str)}
        self.entities = {e["key"]: e["display_name"] for e in practice["entities"]}


def resolved_dates(doc: dict, anchor: date) -> dict[str, date]:
    return {k: resolve_date(v, anchor) for k, v in doc.get("dates", {}).items()}


def addressee_block(doc: dict, ctx: Ctx) -> list[str]:
    a = doc["addressee"]
    name = ctx.people[a["person"]] if "person" in a else ctx.entities[a["entity"]] if "entity" in a else a["text"]
    lines = [name, *a.get("lines", [])]
    if doc.get("show_siren"):
        lines.append("SIREN " + fake_siren(doc["id"] + ":addressee"))
    return lines


def body_values(doc: dict, dates: dict[str, date]) -> dict[str, str]:
    values = {"reference": doc.get("reference", ""), "date": fmt_date(dates["doc"])}
    if "amount" in doc:
        values["amount"] = fmt_amount(doc["amount"]["value"])
    for key in ("due", "period_end"):
        if key in dates:
            values[key] = fmt_date(dates[key])
    return values


def make_pdf(doc: dict, ctx: Ctx, dates: dict[str, date], target: Path) -> None:
    styles = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=styles["Normal"], fontName="Helvetica", fontSize=10.5, leading=15)
    bold = ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold")
    title = ParagraphStyle("title", parent=bold, fontSize=13, spaceBefore=14, spaceAfter=10)
    values = body_values(doc, dates)
    sender = doc["sender"]
    left = [Paragraph(f"<b>{esc(sender['name'])}</b>", base)] + [
        Paragraph(esc(x), base) for x in sender.get("lines", [])
    ]
    right = [Paragraph(esc(x), base) for x in addressee_block(doc, ctx)]
    head = Table([[left, right]], colWidths=[90 * mm, 80 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story = [
        head,
        Spacer(1, 14),
        Paragraph(esc(f"Laval, le {fmt_date(dates['doc'])}"), ParagraphStyle("r", parent=base, alignment=2)),
    ]
    story.append(Paragraph(esc("Objet : " + doc["object"].format_map(values)), title))
    if doc.get("reference"):
        story.append(Paragraph(esc(f"Référence : {doc['reference']}"), base))
    story.append(Spacer(1, 10))
    if doc["template"] == "statement":
        story += statement_story(doc, dates, base, bold)
    else:
        for line in doc["body"]:
            story += [Paragraph(esc(line.format_map(values)), base), Spacer(1, 8)]
        if doc.get("page_two"):
            story.append(PageBreak())
            story.append(Paragraph(esc(f"Facture {doc['reference']}, page 2"), bold))
            story.append(Spacer(1, 8))
            for line in doc["page_two"]:
                story += [Paragraph(esc(line.format_map(values)), base), Spacer(1, 8)]
    SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=doc["id"],
    ).build(story)


def statement_story(doc: dict, dates: dict[str, date], base: ParagraphStyle, bold: ParagraphStyle) -> list:
    iban = fake_iban(doc["account"])
    opening = doc["opening_balance"]
    rows = [["Date", "Nature des opérations", "Débit", "Crédit"]]
    balance = opening
    for r in doc["rows"]:
        d = dates["period_start"] + timedelta(days=r["day"])
        balance += r["amount"]
        debit = fmt_amount(-r["amount"]) if r["amount"] < 0 else ""
        credit = fmt_amount(r["amount"]) if r["amount"] > 0 else ""
        rows.append([d.strftime("%d.%m"), r["label"], debit, credit])
    table = Table(rows, colWidths=[20 * mm, 90 * mm, 30 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, (0, 0, 0)),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    return [
        Paragraph(
            esc(f"RELEVÉ DE COMPTE du {fmt_date(dates['period_start'])} au {fmt_date(dates['period_end'])}"), bold
        ),
        Paragraph(esc(f"IBAN : {iban}"), base),
        Spacer(1, 8),
        Paragraph(esc(f"SOLDE CRÉDITEUR AU {fmt_date(dates['period_start'])} : {fmt_amount(opening)}"), base),
        Spacer(1, 6),
        table,
        Spacer(1, 8),
        Paragraph(esc(f"NOUVEAU SOLDE AU {fmt_date(dates['period_end'])} : {fmt_amount(balance)}"), bold),
    ]


def rasterize(pdf: Path, workdir: Path, dpi: int = 150) -> list[Image.Image]:
    prefix = workdir / "page"
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix)], check=True, capture_output=True)
    return [Image.open(p).convert("RGB") for p in sorted(workdir.glob("page-*.png"))]


def add_noise(img: Image.Image, rng: np.random.Generator, sigma: float) -> Image.Image:
    arr = np.asarray(img, dtype=np.float32)
    arr += rng.normal(0, sigma, arr.shape[:2])[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def save_image_pdf(pages: list[Image.Image], target: Path, dpi: int = 150) -> None:
    pages[0].save(target, "PDF", resolution=dpi, save_all=True, append_images=pages[1:])


def make_scan(pages: list[Image.Image], rotations: list[int], rng: np.random.Generator) -> list[Image.Image]:
    out = []
    for i, page in enumerate(pages):
        img = page.convert("L").rotate(float(rng.uniform(-0.6, 0.6)), resample=Image.BICUBIC, fillcolor=255)
        img = add_noise(img.convert("RGB"), rng, 3.0).convert("L")
        angle = rotations[i] if i < len(rotations) else 0
        out.append(img.rotate(angle, expand=True) if angle else img)
    return out


def perspective_coeffs(dest: list[tuple[float, float]], src: list[tuple[float, float]]) -> list[float]:
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dest, src):
        rows += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        rhs += [u, v]
    return np.linalg.solve(np.array(rows, dtype=np.float64), np.array(rhs, dtype=np.float64)).tolist()


def make_photo(page: Image.Image, rng: np.random.Generator) -> Image.Image:
    w, h = 1600, 1200
    page = page.resize((int(page.width * 0.62), int(page.height * 0.62)), Image.LANCZOS)
    yy, xx = np.mgrid[0:h, 0:w]
    bg = np.stack([120 + 30 * xx / w, 90 + 25 * yy / h, 60 + 10 * xx / w], axis=-1)
    canvas = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    quad = [(300, 60), (1210, 110), (1290, 1150), (240, 1090)]
    src = [(0, 0), (page.width, 0), (page.width, page.height), (0, page.height)]
    coeffs = perspective_coeffs(quad, src)
    warped = page.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    mask = Image.new("L", page.size, 255).transform((w, h), Image.PERSPECTIVE, coeffs, Image.BILINEAR)
    shadow = mask.filter(ImageFilter.GaussianBlur(18)).point(lambda p: int(p * 0.55))
    canvas.paste((20, 15, 10), (14, 18), shadow)
    canvas.paste(warped, (0, 0), mask)
    arr = np.asarray(canvas, dtype=np.float32)
    grad = 1.0 - 0.38 * np.clip((xx / w) * 0.6 + (yy / h) * 0.7 - 0.35, 0, 1)
    blotch = 1.0 - 0.25 * np.exp(-(((xx - 1050) / 260) ** 2 + ((yy - 300) / 180) ** 2))
    arr *= (grad * blotch)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.9))
    return add_noise(img, rng, 5.0)


def make_unreadable(page: Image.Image, rng: np.random.Generator) -> Image.Image:
    small = page.convert("L").resize((page.width // 3, page.height // 3), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(2.2)).resize(page.size, Image.BILINEAR)
    arr = np.asarray(small, dtype=np.float32)
    arr = 150 + (arr - 150) * 0.28
    yy, xx = np.mgrid[0 : arr.shape[0], 0 : arr.shape[1]]
    arr *= 1.0 - 0.55 * np.exp(-(((xx - 0.65 * arr.shape[1]) / 380) ** 2 + ((yy - 0.4 * arr.shape[0]) / 300) ** 2))
    arr[::37, :] *= 0.6
    arr += rng.normal(0, 26, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("L")


def render_doc(doc: dict, ctx: Ctx, out_dir: Path, files: dict[str, Path]) -> dict:
    dates = resolved_dates(doc, ctx.anchor) if doc["render"] != "copy" else {}
    rng = rng_for(doc["id"])
    if doc["render"] == "copy":
        target = out_dir / f"{doc['out']}.pdf"
        shutil.copyfile(files[doc["copy_of"]], target)
        return {"file": target.name, "render": "copy"}
    ext = "jpg" if doc["render"] == "photo" else "pdf"
    target = out_dir / f"{doc['out']}.{ext}"
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        base_pdf = tmpdir / "base.pdf"
        make_pdf(doc, ctx, dates, base_pdf)
        if doc["render"] == "pdf":
            shutil.copyfile(base_pdf, target)
        else:
            pages = rasterize(base_pdf, tmpdir)
            if doc["render"] == "scan":
                save_image_pdf(make_scan(pages, doc["scan"]["rotations"], rng), target)
            elif doc["render"] == "photo":
                make_photo(pages[0], rng).save(target, "JPEG", quality=72)
            elif doc["render"] == "unreadable":
                save_image_pdf([make_unreadable(pages[0], rng)], target)
            else:
                raise ValueError(f"unknown render {doc['render']}")
    info = {"file": target.name, "render": doc["render"], "dates": {k: v.isoformat() for k, v in dates.items()}}
    if "amount" in doc:
        info["amount"] = doc["amount"]
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", required=True, type=date.fromisoformat)
    ap.add_argument("--out", type=Path, default=DEMO_DATA / "synthetic")
    ap.add_argument("--docs", type=Path, default=HERE / "docs.yaml")
    args = ap.parse_args()
    out = args.out.expanduser().resolve()
    if REPO in (out, *out.parents):
        print(f"refusing to write inside the repo: {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    practice = yaml.safe_load(SEED.read_text(encoding="utf-8"))
    docs = yaml.safe_load(args.docs.read_text(encoding="utf-8"))["docs"]
    ctx = Ctx(args.anchor, practice)
    files: dict[str, Path] = {}
    manifest: dict[str, dict] = {}
    errors = 0
    for doc in docs:
        try:
            info = render_doc(doc, ctx, out, files)
            files[doc["id"]] = out / info["file"]
            info["sha256"] = hashlib.sha256(files[doc["id"]].read_bytes()).hexdigest()
            manifest[doc["id"]] = info
            print(f"ok    {doc['id']} -> {info['file']}")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"ERROR {doc['id']}: {exc}", file=sys.stderr)
    (out / "manifest.json").write_text(
        json.dumps({"anchor": args.anchor.isoformat(), "docs": manifest}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    accounts = {d["account"]: {"iban": fake_iban(d["account"])} for d in docs if "account" in d}
    (out / "generated-identifiers.yaml").write_text(
        yaml.safe_dump({"accounts": accounts}, sort_keys=True), encoding="utf-8"
    )
    print(f"{len(docs)} documents, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
