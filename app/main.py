from fastapi import FastAPI

from app.api.errors import service_error_handler
from app.api.routes import router
from app.config import Settings, get_settings
from app.infrastructure.jobs import InMemoryJobRepository
from app.infrastructure.storage import LocalFileStorage
from app.llm.client import MultimodalModelClient, OpenAICompatibleMultimodalClient
from app.models import ServiceError
from app.pipeline import KnowledgeTreeGenerationService


def create_app(
    settings: Settings | None = None,
    model_client: MultimodalModelClient | None = None,
) -> FastAPI:
    config = settings or get_settings()
    storage = LocalFileStorage(config.runtime_dir)
    jobs = InMemoryJobRepository()
    client = model_client or OpenAICompatibleMultimodalClient(config)
    service = KnowledgeTreeGenerationService(config, storage, client)
    application = FastAPI(title=config.app_name)
    application.state.settings = config
    application.state.storage = storage
    application.state.jobs = jobs
    application.state.service = service
    application.add_exception_handler(ServiceError, service_error_handler)
    application.include_router(router)
    return application


app = create_app()
