"""L4 workflow jobs: drafting a reply and building an accountant pack."""

from mona.jobs import app


@app.task(name="generate_draft", queue="llm")
def generate_draft(draft_id: str) -> str:
    from mona.workflow.common import get_ctx
    from mona.workflow.drafts import generate_draft as run

    return run(get_ctx(), draft_id)


@app.task(name="build_export", queue="cpu")
def build_export(export_id: str) -> str:
    from mona.workflow.common import get_ctx
    from mona.workflow.exports import build_export as run

    return run(get_ctx(), export_id)
