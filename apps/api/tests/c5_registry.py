"""The C5 §8.5 fictional registry, as plain data for pure renderer and rules-engine tests."""

from datetime import UTC, date, datetime

from mona.templates import EntityInfo, RenderValues

ENTITIES = {
    "cabinet": EntityInfo("cabinet", "Cabinet Marchand"),
    "studio": EntityInfo("studio", "Studio Numérique", 9, 30),
    "lmnp": EntityInfo("lmnp", "LMNP"),
    "personal": EntityInfo("personal", "Personnel"),
}
SUB_UNITS = {
    ("lmnp", "angers-strasbourg"): "Angers-Strasbourg",
    ("personal", "anna"): "Anna",
    ("personal", "paul"): "Paul",
}
CATEGORIES = {
    "insurance": {"en": "Insurance", "fr": "Assurances", "ro": "Asigurări"},
    "bank": {"en": "Bank", "fr": "Banque", "ro": "Bancă"},
    "annual_accounts": {"en": "Annual accounts", "fr": "Documents annuels", "ro": "Documente"},
    "tax": {"en": "Taxes", "fr": "Impôts et taxes", "ro": "Impozite și taxe"},
    "payment_calls": {"en": "Payment calls", "fr": "Appels de paiement", "ro": "Cereri"},
}
SUBCATEGORIES = {
    ("insurance", "per"): "PER",
    ("insurance", "assurance_vie"): "Assurance vie",
    ("insurance", "prevoyance"): "Prévoyance",
    ("bank", "releve"): "Relevé de compte",
    ("annual_accounts", "bilan"): "Bilan",
    ("annual_accounts", "approbation"): "Approbation des comptes",
    ("tax", "preparation"): "Éléments préparatoires",
    ("payment_calls", "contribution_opco"): "Contribution OPCO",
}
TEMPLATES = {
    "insurance": (
        "{entity}/Assurances/{counterparty}/{sub}/{year}",
        "{date:YYYY-MM-DD}_{counterparty}_{sub}_{reference}",
    ),
    "bank": ("{entity}/Banque/{fy}", "{date:YYYY-MM-DD}_{counterparty}_{sub}"),
    "annual_accounts": (
        "{entity}/Documents annuels/{fy}",
        "{date:YYYY-MM-DD}_{counterparty}_{sub}",
    ),
    "tax": ("{entity}/Impôts et taxes/{year}", "{date:YYYY-MM-DD}_{issuer}_{sub}"),
    "payment_calls": (
        "{entity}/Appels de paiement/{fy}",
        "{date:YYYY-MM-DD}_{counterparty}_{sub}_{reference}",
    ),
}
ARRIVED = datetime(2026, 10, 14, 7, 2, tzinfo=UTC)


def values(
    entity: str | None,
    category: str | None,
    *,
    unit: str | None = None,
    subcategory: str | None = None,
    arrived_at: datetime | date = ARRIVED,
    **kw,
) -> RenderValues:
    sub_label = SUB_UNITS[(entity, unit)] if unit else None
    sub_labels = None
    if subcategory:
        label = SUBCATEGORIES[(category, subcategory)]
        sub_labels = {"en": label, "fr": label, "ro": label}
    return RenderValues(
        entity=ENTITIES[entity] if entity else None,
        arrived_at=arrived_at,
        language="fr",
        sub_unit_label=sub_label,
        category_labels=CATEGORIES[category] if category else None,
        subcategory_labels=sub_labels,
        **kw,
    )
