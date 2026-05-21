from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Freshdesk
    fd_domain: str
    fd_api_key: str

    # Supabase
    supa_url: str
    supa_key: str

    # Pipeline
    initial_sync_date: str = "2026-05-01T00:00:00Z"
    upsert_chunk_size: int = 500
    freshdesk_max_pages: int = 300
    freshdesk_per_page: int = 100

    @property
    def fd_base_url(self) -> str:
        return f"https://{self.fd_domain}.freshdesk.com/api/v2"

    @property
    def fd_auth(self) -> tuple[str, str]:
        return (self.fd_api_key, "X")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
