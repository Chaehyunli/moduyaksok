# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 환경변수 기반 앱 설정 로더
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, DeepEval 파이프라인 성능평가용 키 3종 추가 (tests/eval/ 전용,
#             앱 런타임 로직은 안 씀)
# 2026-08-09, Step2가 쓸 네이버 지역검색 API 키 추가 (네이버 지도 API와는
#             다른 상품 — Step3가 쓸 NAVER_MAP_CLIENT_ID/SECRET과 구분)
# 2026-08-10, Step4 길찾기 프로바이더가 ODsay로 확정되어 ODSAY_API_KEY/
#             ODSAY_REFERER_URL 추가 (네이버 지도 API 키 계획은 폐기 — 기술설계
#             문서 Step4 절 참고). ODSAY_REFERER_URL은 lab.odsay.com에 등록한
#             서비스 URI와 정확히 일치해야 호출이 통과되어 환경별로 값이 다르다.
# 2026-08-10, NAVER_MAP_CLIENT_ID/SECRET 추가 — "네이버 지도 API 키 계획은 폐기"
#             라고 위에 적어뒀던 것과 달리, NCP Maps(Directions 5, 자차 길찾기)가
#             신규 이용 신청이 실제로는 열려 있는 걸 콘솔에서 직접 확인해 다시
#             채택했다(대중교통은 여전히 ODsay). 이 값은 Directions 5 REST 호출용
#             서버 키(Client ID+Secret 둘 다 헤더로 보냄)라 도메인 제한과 무관 —
#             프런트가 Dynamic Map에 쓰는 Client ID(도메인 제한 걸림, VITE_ 접두사)
#             와는 같은 값이지만 용도가 다르다.
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

    # Step2 place_candidates 조회용 (NAVER Developers 포털 발급, 지도 API와 별개).
    naver_search_client_id: str = ""
    naver_search_client_secret: str = ""

    # Step4 enrich_routes용 (lab.odsay.com 발급). 서비스 플랫폼을 URI로 등록했기
    # 때문에 호출 시 Referer 헤더를 이 값과 맞춰줘야 한다.
    odsay_api_key: str = ""
    odsay_referer_url: str = "localhost:8000"

    # Step4 자차 옵션용 (NCP Maps Directions 5, ncloud.com Application "moduyaksok"
    # 에서 발급). Directions/Geocoding 등 서버 REST 호출은 이 Secret까지 헤더에
    # 실어 보내는 것 자체가 인증이라 도메인 제한이 없다 — 개발/배포 환경 구분 없이
    # 같은 값을 쓴다.
    naver_map_client_id: str = ""
    naver_map_client_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
