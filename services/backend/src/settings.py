from pydantic import Field
from generated.settings import Settings as GeneratedSettings


class Settings(GeneratedSettings):
    max_upload_bytes: int = Field(default=10485760, ge=1, le=10485760)
    max_image_pixels: int = Field(default=25000000, ge=1, le=25000000)
    outbox_concurrency: int = Field(default=2, ge=1, le=10)
    lan_ip: str = "127.0.0.1"
    image_provider: str = "fake"
    polza_image_model: str = "openai/gpt-image-1.5"
