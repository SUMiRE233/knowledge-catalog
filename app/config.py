from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "教学周期知识目录生成器"
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    runtime_dir: Path = Path("runtime")
    max_upload_size_mb: int = 25
    allowed_image_types: Annotated[list[str], NoDecode] = [
        "image/png",
        "image/jpeg",
        "image/webp",
    ]
    pdf_render_dpi: int = 160
    enable_image_enhancement: bool = True
    enable_ocr_fallback: bool = False
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str | None = None
    llm_timeout_seconds: float = 120
    llm_max_retries: int = 2
    llm_max_images_per_request: int = 4
    llm_enable_thinking: bool | None = None
    llm_max_output_tokens: int = 16384
    default_grade_range: str = "全部"
    store_page_images: bool = True
    expose_page_images: bool = False
    log_level: str = "INFO"

    @field_validator("allowed_image_types", mode="before")
    @classmethod
    def parse_types(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
