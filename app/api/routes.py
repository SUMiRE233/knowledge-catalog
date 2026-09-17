from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import (
    get_jobs,
    get_service,
    get_settings_from_app,
    get_storage,
)
from app.models import (
    GenerationOptions,
    JobError,
    JobRecord,
    ServiceError,
)
from app.publishing import PUBLIC_ARTIFACTS

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


async def run_generation(job_id, stored, options, jobs, service) -> None:
    record = await jobs.get(job_id)
    record.status = "processing"
    await jobs.update(record)

    async def progress(stage, value):
        current = await jobs.get(job_id)
        current.stage = stage
        current.progress = value
        await jobs.update(current)

    try:
        result = await service.generate(stored, options, progress)
        record = await jobs.get(job_id)
        record.status = "succeeded"
        record.progress = 100
        record.result = {
            "knowledge_tree": result.tree.model_dump(mode="json"),
            "validation_report": result.validation_report.model_dump(mode="json"),
            "artifacts": result.artifacts,
        }
        await jobs.update(record)
    except ServiceError as exc:
        record = await jobs.get(job_id)
        record.status = "failed"
        record.error = JobError(code=exc.code, message=exc.message)
        await jobs.update(record)
    except Exception:
        record = await jobs.get(job_id)
        record.status = "failed"
        record.error = JobError(
            code="INTERNAL_PROCESSING_ERROR",
            message="任务处理发生内部错误",
        )
        await jobs.update(record)


@router.post("/api/v1/knowledge-trees/jobs", status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    settings: Annotated[object, Depends(get_settings_from_app)],
    storage: Annotated[object, Depends(get_storage)],
    jobs: Annotated[object, Depends(get_jobs)],
    service: Annotated[object, Depends(get_service)],
    selected_range: Annotated[str, Form(alias="range")] = "全部",
    enhance_images: Annotated[bool, Form()] = True,
    use_ocr_fallback: Annotated[bool, Form()] = False,
    document_profile: Annotated[
        Literal["general", "primary_dskp_sjkc"],
        Form(),
    ] = "general",
):
    accepted = {"application/pdf", *settings.allowed_image_types}
    suffix = Path(file.filename or "").suffix.lower()
    allowed_suffixes = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
    if file.content_type not in accepted and suffix not in allowed_suffixes:
        raise ServiceError("INVALID_FILE_TYPE", "仅支持 PDF、PNG、JPEG 和 WEBP")
    job_id = str(uuid4())
    stored = await storage.save_upload(job_id, file, settings.max_upload_size_bytes)
    record = JobRecord(job_id=job_id)
    await jobs.create(record)
    options = GenerationOptions(
        selected_range=selected_range,
        enhance_images=enhance_images,
        use_ocr_fallback=use_ocr_fallback,
        document_profile=document_profile,
    )
    background_tasks.add_task(run_generation, job_id, stored, options, jobs, service)
    return {
        "job_id": job_id,
        "status": "pending",
        "status_url": f"/api/v1/knowledge-trees/jobs/{job_id}",
        "result_url": f"/api/v1/knowledge-trees/jobs/{job_id}/result",
    }


@router.get("/api/v1/knowledge-trees/jobs/{job_id}")
async def get_job(job_id: str, jobs: Annotated[object, Depends(get_jobs)]):
    record = await jobs.get(job_id)
    return record.model_dump(mode="json", exclude={"result"})


@router.get("/api/v1/knowledge-trees/jobs/{job_id}/result")
async def get_result(job_id: str, jobs: Annotated[object, Depends(get_jobs)]):
    record = await jobs.get(job_id)
    if record.status != "succeeded":
        raise ServiceError("JOB_NOT_READY", "任务结果尚未就绪", status_code=409)
    return record.result


@router.get("/api/v1/knowledge-trees/jobs/{job_id}/artifacts/{artifact_name}")
async def get_artifact(
    job_id: str,
    artifact_name: str,
    jobs: Annotated[object, Depends(get_jobs)],
    storage: Annotated[object, Depends(get_storage)],
):
    record = await jobs.get(job_id)
    if record.status != "succeeded":
        raise ServiceError("JOB_NOT_READY", "任务结果尚未就绪", status_code=409)
    if artifact_name not in PUBLIC_ARTIFACTS:
        raise ServiceError("ARTIFACT_NOT_FOUND", "artifact 不存在", status_code=404)
    path = storage.artifact_path(job_id, artifact_name)
    return FileResponse(path, filename=artifact_name)
