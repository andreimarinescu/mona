"""Synthetic archive for the spike; fictional names and amounts."""

from typing import Any

ENTITY_PRACTICE = ("ent_cabinet", "Cabinet Marchand")
ENTITY_PERSONAL = ("ent_personnel", "Personnel")

DOCUMENTS: dict[str, dict[str, Any]] = {
    "doc_urssaf_q3": {
        "title": "URSSAF appel de cotisation T3",
        "entity": ENTITY_PRACTICE,
        "category": "tax",
        "path": ["Cabinet Marchand", "2026", "Cotisations sociales"],
        "fileName": "2026-09-22_URSSAF_Appel_T3.pdf",
        "date": "2026-09-22",
        "amount": 1284.00,
        "due": "2026-10-14",
        "confidence": 0.93,
    },
    "doc_agipi_per": {
        "title": "AGIPI PER avis d'échéance",
        "entity": ENTITY_PERSONAL,
        "category": "insurance",
        "path": ["Personnel", "Assurances", "AGIPI"],
        "fileName": "2026-09-10_AGIPI_PER_Avis.pdf",
        "date": "2026-09-10",
        "amount": 520.00,
        "due": None,
        "confidence": 0.71,
    },
    "doc_agipi_av": {
        "title": "AGIPI Assurance Vie relevé annuel",
        "entity": ENTITY_PERSONAL,
        "category": "insurance",
        "path": ["Personnel", "Assurances", "AGIPI"],
        "fileName": "2026-08-30_AGIPI_AV_Releve.pdf",
        "date": "2026-08-30",
        "amount": 1200.00,
        "due": None,
        "confidence": 0.66,
    },
    "doc_edf_sept": {
        "title": "EDF facture septembre",
        "entity": ENTITY_PRACTICE,
        "category": "invoice",
        "path": ["Cabinet Marchand", "2026", "Énergie"],
        "fileName": "2026-09-18_EDF_Facture.pdf",
        "date": "2026-09-18",
        "amount": 214.37,
        "due": "2026-10-05",
        "confidence": 0.97,
    },
}


def search(query: str, entity: str | None = None) -> list[str]:
    words = query.lower().split()
    return [
        doc_id
        for doc_id, d in DOCUMENTS.items()
        if any(w in d["title"].lower() for w in words)
        and (not entity or entity.lower() in d["entity"][1].lower())
    ]


def document_summary(doc_id: str) -> dict[str, Any] | None:
    """A subset of C1 `DocumentSummary`."""
    d = DOCUMENTS.get(doc_id)
    if d is None:
        return None
    return {
        "id": doc_id,
        "title": d["title"],
        "originalName": d["fileName"],
        "fileName": d["fileName"],
        "path": d["path"],
        "location": "archive",
        "entityId": d["entity"][0],
        "entityName": d["entity"][1],
        "categoryId": d["category"],
        "date": d["date"],
        "amount": {"value": d["amount"], "currency": "EUR"},
        "dueDate": d["due"],
        "status": "filed",
        "reasons": [],
        "confidence": d["confidence"],
        "arrivedAt": f"{d['date']}T08:00:00Z",
        "source": "drop",
    }


def interview_payload(
    interview_id: str, question_id: str, topic: str, created_at: str
) -> dict[str, Any]:
    """A C1 `Interview` with one ready question and three options."""
    affects = search(topic)
    return {
        "id": interview_id,
        "kind": "on_demand",
        "status": "ready",
        "questions": [
            {
                "id": question_id,
                "ordinal": 1,
                "question": f"Who holds the {topic} contracts: you personally, or the practice?",
                "lang": "en",
                "affects": affects,
                "affectsCount": len(affects),
                "evidence": [],
                "options": [
                    {
                        "id": "opt_1",
                        "label": "Always personal, split by insured person",
                        "suggested": True,
                        "ruleDraft": None,
                    },
                    {"id": "opt_2", "label": "The practice pays them", "ruleDraft": None},
                    {
                        "id": "opt_3",
                        "label": "Shared between the practice and personal",
                        "ruleDraft": None,
                    },
                ],
                "suggestionConfidence": 0.72,
                "status": "open",
                "answer": None,
            }
        ],
        "batchId": None,
        "createdAt": created_at,
    }
