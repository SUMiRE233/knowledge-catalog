import asyncio
from datetime import UTC, datetime
from typing import Protocol

from app.models import JobRecord, ServiceError


class JobRepository(Protocol):
    async def create(self, record: JobRecord) -> None: ...
    async def get(self, job_id: str) -> JobRecord: ...
    async def update(self, record: JobRecord) -> None: ...


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: JobRecord) -> None:
        async with self._lock:
            self._jobs[record.job_id] = record.model_copy(deep=True)

    async def get(self, job_id: str) -> JobRecord:
        async with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                raise ServiceError("JOB_NOT_FOUND", "任务不存在", status_code=404)
            return record.model_copy(deep=True)

    async def update(self, record: JobRecord) -> None:
        async with self._lock:
            record.updated_at = datetime.now(UTC)
            self._jobs[record.job_id] = record.model_copy(deep=True)
