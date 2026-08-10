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

## 파일 네이밍
- `app/pipeline/` 밑 파일은 `{역할}_step{N}.py` 형식(`normalize_step1.py`,
  `generate_step2.py` 등) — 파일명만 보고 몇 번째 단계인지 바로 알 수 있게.

## DB 제약
- 값이 제한된 문자열 컬럼(enum처럼 쓰는 것)은 Postgres ENUM 타입 대신 문자열 +
  CHECK 제약으로 건다. 이 프로젝트가 쓰는 SQLModel 버전은 `table=True` 모델의
  컬럼에 `Literal` 타입을 못 붙인다(시도하면 컬럼 매핑 단계에서 에러) — "앱 코드
  타입 힌트가 이미 값을 제한하니 DB 제약은 안 걸어도 된다"고 가정하지 말 것.
