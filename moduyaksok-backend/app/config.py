# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 환경변수 기반 앱 설정 로더
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, DeepEval 파이프라인 성능평가용 키 3종 추가 (tests/eval/ 전용,
#             앱 런타임 로직은 안 씀)
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

    # DeepEval 파이프라인 성능평가 테스트 전용 키(tests/eval/). 사용자 BYOK 키와
    # 무관 — 우리 자신이 파이프라인 품질을 채점할 때만 씀. upstage → openai →
    # anthropic 순으로 시도해서 첫 번째로 유효한 것을 쓴다 (tests/eval/_provider.py).
    deepeval_upstage_api_key: str | None = None
    deepeval_openai_api_key: str | None = None
    deepeval_anthropic_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
