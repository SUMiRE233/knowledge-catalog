import re
from pathlib import Path
from typing import Protocol

from fastapi import UploadFile

from app.models import ServiceError, StoredFile


class FileStorage(Protocol):
    async def save_upload(self, job_id: str, upload: UploadFile, max_bytes: int) -> StoredFile: ...

    def output_dir(self, job_id: str) -> Path: ...

    def artifact_path(self, job_id: str, name: str) -> Path: ...


class LocalFileStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    @staticmethod
    def safe_name(filename: str | None) -> str:
        name = Path((filename or "upload").replace("\\", "/")).name
        name = re.sub(r"[^\w.\-()\u4e00-\u9fff]", "_", name, flags=re.UNICODE)
        return name[:180] or "upload"

    def job_dir(self, job_id: str) -> Path:
        return self.root / "jobs" / job_id

    def output_dir(self, job_id: str) -> Path:
        path = self.job_dir(job_id) / "output"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_upload(self, job_id: str, upload: UploadFile, max_bytes: int) -> StoredFile:
        input_dir = self.job_dir(job_id) / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        safe = self.safe_name(upload.filename)
        target = input_dir / safe
        size = 0
        with target.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise ServiceError("FILE_TOO_LARGE", "上传文件超过大小限制", status_code=413)
                handle.write(chunk)
        if size == 0:
            target.unlink(missing_ok=True)
            raise ServiceError("EMPTY_FILE", "上传文件为空")
        return StoredFile(
            job_id=job_id,
            original_filename=upload.filename or safe,
            safe_filename=safe,
            path=target,
            content_type=upload.content_type or "application/octet-stream",
            size_bytes=size,
        )

    def artifact_path(self, job_id: str, name: str) -> Path:
        if Path(name).name != name or "/" in name or "\\" in name:
            raise ServiceError("ARTIFACT_NOT_FOUND", "artifact 不存在", status_code=404)
        path = (self.output_dir(job_id) / name).resolve()
        if path.parent != self.output_dir(job_id).resolve() or not path.is_file():
            raise ServiceError("ARTIFACT_NOT_FOUND", "artifact 不存在", status_code=404)
        return path
