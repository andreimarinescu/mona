"""C6 §3.1: the two hooks L1 calls after its pipeline commits (no-ops until L4's module)."""


def on_batch_done(batch_id: str) -> None:
    """Once, after the commit that set the batch `done` (C1 §4.1)."""


def on_document_settled(batch_id: str) -> None:
    """After every commit that moved a document of a running batch out of a running stage."""
