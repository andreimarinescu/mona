from procrastinate.jobs import Status

from mona import jobs


async def test_ping_runs_only_on_its_own_queue():
    async with jobs.app.open_async():
        manager = jobs.app.job_manager
        for task, queue, other in [(jobs.ping_llm, "llm", "cpu"), (jobs.ping_cpu, "cpu", "llm")]:
            job_id = await task.defer_async()
            await jobs.app.run_worker_async(queues=[other], wait=False)
            assert await manager.get_job_status_async(job_id) == Status.TODO
            await jobs.app.run_worker_async(queues=[queue], wait=False)
            assert await manager.get_job_status_async(job_id) == Status.SUCCEEDED
