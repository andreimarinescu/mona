"""C6 jobs on Procrastinate: the trigger check, generation, and the stale sweep."""

from mona.jobs import app


@app.task(name="debrief_check", queue="cpu")
def debrief_check(batch_id: str) -> list[str]:
    from mona.interviews.triggers import debrief_check as check
    from mona.workflow.common import get_ctx

    return check(get_ctx(), batch_id)


@app.task(name="generate_interview", queue="llm")
def generate_interview(interview_id: str) -> str:
    from mona.interviews.generate import generate_interview as run
    from mona.workflow.common import get_ctx

    return run(get_ctx(), interview_id)


@app.periodic(cron="* * * * *")
@app.task(name="sweep_interviews", queue="cpu", queueing_lock="sweep_interviews")
def sweep_interviews(timestamp: int) -> int:
    from mona.interviews.service import sweep_stale
    from mona.workflow.common import get_ctx

    return len(sweep_stale(get_ctx()))
