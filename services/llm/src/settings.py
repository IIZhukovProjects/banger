from typing import Literal
from pydantic import Field, SecretStr
from generated.settings import Settings as GeneratedSettings


class Settings(GeneratedSettings):
    image_provider: Literal["fake", "polza"] = "fake"
    polza_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    # Fallback for jobs created before the provider URL was stored.
    image_provider_base_url: str = "https://polza.ai/api/v1"
    polza_api_origin: str = ""
    image_job_concurrency: int = Field(default=2, ge=1, le=10)
    image_job_timeout_seconds: int = Field(default=360, ge=30, le=1800)
    image_queue_limit: int = Field(default=1000, ge=1, le=10000)
