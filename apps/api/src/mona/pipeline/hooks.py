"""Calls made after a pipeline transaction commits; C6 (L1-M3) fills them in."""

from mona.services.context import Ctx


def batch_done(ctx: Ctx, batch_id: str) -> None:
    """C1 §4.1: once, after the commit that marked the batch `done`."""
    if ctx.on_batch_done:
        ctx.on_batch_done(batch_id)


def document_settled(ctx: Ctx, batch_id: str) -> None:
    """After any commit that moved one of the batch's documents out of a running stage."""
    if ctx.on_document_settled:
        ctx.on_document_settled(batch_id)
