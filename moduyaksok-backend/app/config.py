# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 환경변수 기반 앱 설정 로더
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = "development"

    database_url: str = "sqlite:///./dev.db"

    jwt_secret_key: str = "dev-secret-change-me"
    google_client_id: str = ""

    credential_encryption_key: str = ""

    # 개발 편의용 폴백 키. ENV=development 일 때만 사용된다.
    anthropic_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
