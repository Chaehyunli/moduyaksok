# 모두약속 — 백엔드 개발 방법론

실행/환경변수/구조/테스트 명령어는 `README.md` 참고. 여기는 "왜 이렇게 개발하기로
했는지"만 남긴다 — 새 기능을 이 프로젝트 방식대로 만들 때 참고할 것.

## 테스트 — 유닛 vs 성능평가(eval)를 분리해서 유지할 것
- `tests/*.py` (기본 `pytest`): provider SDK를 항상 `monkeypatch`로 mock. "입력을
  올바르게 조립하고 응답을 올바르게 파싱하는지"만 검증 — 실제 키 없이 항상
  통과해야 함.
- `tests/eval/*.py` (`pytest -m eval`): mock 없이 실제 LLM을 호출해서 DeepEval의
  `GEval`(LLM-judge)로 "이 단계의 판단이 실제로 괜찮은가"를 채점. 기본 `pytest`
  실행에서 자동 제외됨(`pyproject.toml`의 `addopts = "-m 'not eval'"`) — 과금·
  네트워크 의존이라 일반 개발 루프와 분리.
- 새 파이프라인 단계를 구현할 때마다 **두 종류 다** 만들 것. 유닛 테스트만으로는
  "모델이 실제로 잘하는지"를 절대 못 잡는다 — Step1의 "빈 입력에 없는 내용을
  지어내는 할루시네이션" 버그는 유닛 테스트(mock)로는 안 보였고, 실제 eval을
  돌려보고서야 발견함.
- eval 점수가 낮게 나오면 바로 "모델이 못한다"고 결론 내지 말고 judge의 `reason`을
  먼저 읽을 것 — GEval `criteria` 문구 자체가 애매해서 judge가 헷갈리는 경우가
  실제로 있었다 (`verifiable=true/false`라는 불리언을 "객관적"/"주관적" 문자열로
  착각해서 맞는 답을 감점한 사례, 2026-08-07). criteria는 값의 실제 타입/형태를
  명확히 못박아서 쓸 것.

## 모델 티어(LOW/MID/HIGH) — 작업 성격으로 정하고, 스키마 바뀌면 재검증
- `app/pipeline/models.py`에서 provider × 티어 → 모델 ID를 한 곳에서 관리. 새 단계
  만들 때 "단순 추출/분류(LOW)인지, 어느 정도 창의성 필요(MID)인지, 여러 결과를
  비교/판단해야 하는지(HIGH)"로 먼저 정하고 시작할 것.
- 티어 가정은 스키마가 바뀌면 재검증해야 한다 — Step1이 태그를 `list[str]`로 뽑을
  땐 LOW로 충분했는데, `PreferenceTag`(태그명 + `verifiable` 불리언, 필드 2개짜리
  객체)로 스키마가 복잡해지자 LOW 모델(`solar-mini`)이 `disliked_text`가 비었을 때
  few-shot 예시 내용을 베끼거나 `liked` 항목을 `disliked`에 중복 삽입하는 문제가
  DeepEval 골든셋으로 실측 확인됨. MID(`solar-pro`)로 올리자 같은 골든셋에서
  9/9 통과(0.80~1.00)로 즉시 해결(2026-08-07). "간단해 보이는 작업"이라도 출력
  스키마가 복잡해지면 티어를 다시 확인할 것.

## Structured output — provider 늘어난다고 분기부터 늘리지 말고 먼저 실측
- `app/services/structured_llm.py`의 `call_structured()`가 provider별 구조화 출력
  방식을 통일. Claude는 tool use, GPT/Solar는 `client.beta.chat.completions.parse()`
  공용 — Solar가 openai SDK 호환이라고 최신 기능(`.parse()`, `response_format`
  strict json_schema)까지 지원할 거라 가정하지 않고, 실제로 스크립트를 짜서
  찔러본 뒤에 "GPT/Solar 공용 1갈래"로 분기를 3개에서 2개로 줄임(2026-08-07).
  새 provider를 추가할 때도 API 문서만 보고 가정하지 말고 먼저 작은 스크립트로
  실측할 것.

## 프롬프트 엔지니어링 — 태스크 성격에 맞는 기법을 쓸 것, 하나로 통일하지 말 것
- **추출/분류 작업(Step1)**: RTF(Role/Task/Format) 뼈대 + few-shot. few-shot 예시는
  추상적인 걸 만들지 말고 **실제 관측된 실패 사례를 그대로 예시로 박아넣는 게**
  가장 효과적이었음 (빈 입력 할루시네이션 버그를 예시 3번으로 직접 겨냥,
  `normalize_step1.py`의 `_SYSTEM_PROMPT` 참고).
- **설득력 있는 문장을 써야 하는 생성 단계(Step3의 `why_recommended` 등)**: 아직
  미구현이지만 CO-STAR(Context/Objective/Style/Tone/Audience/Response format)가
  더 맞을 가능성이 큼 — 톤·스타일이 중요한 콘텐츠 생성에 맞는 프레임워크라서.
  Step3 구현할 때 판단할 것.
- CARE/CREATE 같은 마케팅 카피용 프레임워크는 이 프로젝트 태스크들과는 안 맞음 —
  프레임워크를 먼저 고르지 말고 태스크 성격(추출 vs 생성 vs 판단)부터 파악할 것.
- few-shot 예시가 많거나 구체적일수록, 특히 작은 모델은 예시 내용을 실제 입력과
  무관하게 베껴 쓰는 부작용이 있을 수 있다 (Step1 LOW 티어에서 실측됨) — 예시
  수·구체성을 늘릴 때는 이 부작용도 같이 eval로 확인할 것.

## "검증 불가능한 정보"를 다루는 패턴
- LLM이 뽑아낸 정보 중에는 나중에 실제 데이터로 확인 가능한 것(예: 태그가 실존
  장소 카테고리와 일치하는지)과, 확인할 데이터 자체가 없는 것(예: "사람 많은 곳"
  같은 혼잡도·분위기)이 섞여 있다.
- 이런 경우 확인 가능/불가능을 명시적으로 태깅해서(`PreferenceTag.verifiable`)
  다음 단계로 넘기고, 다음 단계는 확인 가능한 것만 하드 제약(반드시 보장)으로,
  불가능한 건 소프트 신호(참고만 하되 보장 안 함)로 다르게 취급하게 설계할 것.
  사용자에게 보여주는 문장도 검증 못 한 걸 확신하는 것처럼 쓰지 말 것(hedge된
  표현 — "사람이 없습니다"가 아니라 "비교적 한산한 편인 곳으로 골랐어요").

## BYOK 키 보안 — 알려진 한계, 지금은 구조 안 바꾸기로 함
- 서버(`CREDENTIAL_ENCRYPTION_KEY`를 가진 쪽)는 DB의 어떤 사용자 키든 복호화
  가능 — 구조적 한계. 검토한 대안(클라이언트 사이드 직접 호출, PIN 기반 envelope
  encryption)과 지금 구조를 유지하기로 한 이유는 `docs/기술설계_2026-08-06.md`
  §3.4 참고.
- 나중에 구조를 바꿔야 할 때를 대비해, 파이프라인 함수(`normalize_conditions` 등)는
  항상 **이미 복호화된 평문 `api_key: str`을 파라미터로** 받게 유지할 것 —
  "어떻게 저장/복호화했는지"와 "그 키로 뭘 하는지"를 분리해두면, 저장 방식을
  나중에 바꿔도 파이프라인 코드(`app/pipeline/*.py`)는 안 건드려도 된다.

## 외부 API 호출량 제어 — 결정론적 하드 룰은 LLM 판단 대신 코드로, rate limit은 처음부터 단순하게
- Step2/Step3에서 "LLM에게 프롬프트로만 지시하고 끝내지 않는다" 원칙(위 "검증
  불가능한 정보" 절과 같은 결)을 소싱 단계에도 적용한 사례: 태그 매칭(`liked_tags`/
  `disliked_tags`)을 category/title 텍스트로 LLM이 추측하게 두는 대신, verifiable
  태그마다 `"{region} {tag}"` 검색을 따로 호출해서 결정론적 근거(`matched_tag`)를
  만들고, 그걸로 하드 룰(같은 태그 중복 반영 등)을 코드가 강제한다
  (`naver_local_search.py`/`synthesize_step3.py`, 2026-08-11). 프롬프트 지시는
  1차 방어로 남겨두고, 결정 가능한 부분은 항상 코드가 2차로 강제하는 이중 구조를
  기본으로 삼을 것.
- rate limiter(`app/services/rate_limiter.py`)는 처음엔 프로세스 전역 토큰버킷
  (순수 FIFO)으로 시작했다가, 한 요청이 콜을 잔뜩 큐에 넣으면 다른 요청이 여러
  초씩 굶을 수 있다는 지적을 받고 세션(=요청) 단위 라운드로빈으로 바로
  업그레이드했다(2026-08-11, `_RoundRobinLimiter`). 다만 "정교한 스케줄러를
  처음부터 만들지 않는다"는 태도 자체는 유효 — 실제로 한 것도 새 자료구조를
  더 얹은 게 아니라, 기존 토큰버킷(충전량 `_tokens`, 상한 `rate`)에 "토큰이
  생길 때마다 어느 세션 차례인지"만 라운드로빈으로 고르는 얇은 레이어를 씌운
  것뿐이다 — 세션이 하나뿐이면 경쟁 상대가 없으니 기존 토큰버킷과 완전히
  동일하게(버스트 포함) 동작하고, 세션이 여럿일 때만 라운드로빈이 실제로
  개입한다. **필요성이 구체적으로 지적되기 전엔 더 무거운 걸 먼저 넣지 않는다**
  는 원칙은 그대로 지키고, 실제로 필요해졌을 때 최소한의 추가로 확장하는 게
  이 프로젝트가 다른 곳(도보 정밀 경로 TMAP 등)에서도 반복하는 결.
- 일일 호출 카운터처럼 여러 프로세스/워커에서 공유돼야 하는 상태는 in-memory가
  아니라 외부 저장소(Redis)에 둘 것 — in-memory는 프로세스 재시작 시 리셋되고,
  멀티 워커/인스턴스로 스케일하면 프로세스마다 따로 카운트해서 전역 한도가
  깨진다. 부족한 자원을 확보할 때는(`reserve_daily_budget`) 요청 자체를 실패시키기
  보다 "확보되는 만큼만 주고 나머지는 호출부가 알아서 줄여 쓰게" 하는 쪽을
  기본으로 — 하드 실패보다 부분 결과로 degrade하는 게 이 프로젝트가 선호하는 방향.
- 유닛 테스트는 rate limiter/Redis도 provider SDK와 똑같이 취급한다 —
  `tests/conftest.py`의 autouse fixture가 `acquire_call_slot`/`reserve_daily_budget`
  을 기본으로 무력화해서, 개별 테스트가 실제 wall-clock 대기나 Redis 연결 없이
  항상 빠르게 통과한다. rate limiter 자체의 동작(토큰버킷 타이밍, 일일 카운터)은
  `tests/test_rate_limiter.py`가 이 패치 없이 실제 타이밍 + `fakeredis`로 따로
  검증한다.

## 파일 네이밍
- `app/pipeline/` 밑 파일은 `{역할}_step{N}.py` 형식(`normalize_step1.py`,
  `generate_step2.py` 등) — 파일명만 보고 몇 번째 단계인지 바로 알 수 있게.

## DB 제약
- 값이 제한된 문자열 컬럼(enum처럼 쓰는 것)은 Postgres ENUM 타입 대신 문자열 +
  CHECK 제약으로 건다. 이 프로젝트가 쓰는 SQLModel 버전은 `table=True` 모델의
  컬럼에 `Literal` 타입을 못 붙인다(시도하면 컬럼 매핑 단계에서 에러) — "앱 코드
  타입 힌트가 이미 값을 제한하니 DB 제약은 안 걸어도 된다"고 가정하지 말 것.
