"""进程内后台任务。大表转换不占用请求线程超过同步等待上限，可查询进度和取消。"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class Job:
    id: str
    status: str = "queued"
    progress: int = 0
    result: Any = None
    error: str = ""
    cancel_event: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)


class JobRunner:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, fn: Callable[[Job], Any], *, sync_timeout: float) -> tuple[Job, bool]:
        job = Job(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job

        def target() -> None:
            with self._lock:
                if job.cancel_event.is_set():
                    job.status = "cancelled"
                    job.done.set()
                    return
                job.status = "running"
            try:
                result = fn(job)
                with self._lock:
                    if job.cancel_event.is_set() or job.status == "cancelled":
                        job.status = "cancelled"
                        job.result = None
                    else:
                        job.result = result
                        job.status = "done"
                        job.progress = 100
            except Exception as exc:  # noqa: BLE001
                name = exc.__class__.__name__
                with self._lock:
                    if name == "SnapshotCancelled" or job.cancel_event.is_set() or job.status == "cancelled":
                        job.status = "cancelled"
                    else:
                        job.status = "failed"
                        job.error = str(exc)
            finally:
                job.done.set()

        threading.Thread(target=target, name=f"fba-job-{job.id[:8]}", daemon=True).start()
        finished = job.done.wait(sync_timeout) if sync_timeout > 0 else False
        return job, finished

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        with self._lock:
            job.cancel_event.set()
            if job.status in {"queued", "running"}:
                job.status = "cancelled"
        return job


RUNNER = JobRunner()


def public_job(job: Job, *, include_result: bool = True) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
    }
    if job.error:
        body["error"] = job.error
    if include_result and job.status == "done":
        body["result"] = job.result
    return body
