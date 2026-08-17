# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 파이프라인 단계별로 쓸 provider별 모델을 성능 티어로 관리
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-12, openai/upstage TODO placeholder를 provider 간 가격대가 맞는 실제
#             모델로 교체. LOW 티어가 그동안 upstage만 실측(solar-mini 탈락 →
#             solar-pro로 교체)된 상태로 anthropic/openai에도 그대로 적용되고
#             있었음 — LOW를 "solar-pro/gpt-5-mini급 소형 모델"로 재정의해 세
#             provider의 LOW가 비슷한 가격대(출력 기준 대략 $0.6~5/1M)를 갖게
#             정렬. MID/HIGH도 동일 기준(가격이 가장 가까운 모델)으로 맞춤 —
#             근거 가격은 하단 표 참고.
# 2026-08-12(2차), scripts/compare_providers_eval.py로 provider별 "일정 하나"
#             실비용을 실측하다가, 각 step 파일의 TIER 상수가 이 문서(아래 표)가
#             말하는 것과 실제로는 어긋나 있던 걸 발견 — Step1이 LOW가 아니라
#             MID로, Step2가 MID가 아니라 HIGH로 돌고 있었다(각각 stale한 이유로
#             격상된 뒤 안 내려간 것). 이 발견을 계기로 "step 로직에서는 최대한
#             HIGH를 안 쓴다"는 방향으로 Step1(MID→LOW)/Step2(HIGH→MID)를
#             내렸다. Step3도 같이 내렸다가(HIGH→MID) golden_step3.py 재검증에서
#             Claude가 _JudgmentBatch 스키마를 75% 확률로 못 지키고 크래시하는 걸
#             확인해 바로 원복 — Step3는 아직 HIGH가 필요하다(synthesize_step3.py
#             2026-08-12 변경사항 참고). 결과적으로 지금은 Step1=LOW, Step2=MID,
#             Step3=HIGH. 실제 TIER 배정은 각 step 파일(normalize_step1.py/
#             generate_step2.py/synthesize_step3.py) 상단의 TIER 상수가 항상
#             최신 진실이다 — 이 문서(및 아래 docstring)가 아니라.
# 2026-08-17, google(Gemini) provider 추가 — 사용자 요청으로 GPT/Solar를 추가할
#             때처럼 실제 키로 찔러보고 가격표를 실측한 뒤 넣는 게 원칙이지만
#             (백엔드 CLAUDE.md "Structured output" 절), 지금은 등록된 Gemini
#             키가 없어 GPT 추가 때와 동일한 수준(가격만 공개 자료 기준으로
#             정렬, structured_llm.call_structured() 실제 호출은 아직 안 해봄)의
#             "예상" 상태로 우선 넣는다 — 실제 키가 생기면 다른 provider들처럼
#             작은 스크립트로 찔러보고 이 표·아래 가격 주석을 실측치로 갱신할 것.
#             모델 ID는 구글이 공개한 크기 순서(flash-lite < flash < pro)만
#             신뢰하고 골랐다 — 가격 숫자는 아직 안 넣음(실측 전엔 틀린 숫자를
#             주석에 박아두는 게 더 위험하다고 판단).
# ------------------------------------------------------------------
from enum import StrEnum


class ModelTier(StrEnum):
    """provider·모델의 성능/가격 등급. 어느 step이 어느 티어를 쓰는지는 이 파일이
    아니라 각 step 파일(normalize_step1.py/generate_step2.py/synthesize_step3.py)
    상단의 TIER 상수가 결정한다 — 예전에 여기 docstring과 실제 TIER 배정이
    어긋난 채로 방치된 적이 있어서(2026-08-12(2차) 변경사항 참고), 이 파일은
    "티어별 대략적 성격"만 설명하고 "무슨 step이 어느 티어냐"는 단언하지 않는다.

    LOW  — 소형/저렴. 구조화 추출/분류처럼 창의성 불필요, 속도·비용 우선인 작업.
    MID  — 중형. 여러 결과를 비교/생성하지만 opus급까지는 필요 없다고 실측으로
           확인된 작업.
    HIGH — 최상급(claude-opus-5 등). 비용이 커서 파이프라인 step 로직에서는
           최대한 피하는 게 방향이지만, 강제 원칙은 아니다 — 실제로 Step3는
           MID로 내렸다가 Claude에서 구조화 출력 크래시가 75%까지 뛰어서
           HIGH로 되돌아갔다(2026-08-12). DeepEval judge(tests/eval/conftest.
           ProviderJudgeModel)는 항상 HIGH를 쓴다.
    """

    LOW = "low"
    MID = "mid"
    HIGH = "high"


# 각 provider가 실제로 어떤 모델 ID를 쓰는지는 여기서만 관리한다. 파이프라인 코드는
# provider 이름과 ModelTier만 알면 되고, 모델을 교체하고 싶으면 이 표만 고치면 된다.
#
# 2026-08-12 기준 각 provider 공식 가격 페이지 실측(1M 토큰당, 입력/출력 USD):
#   LOW  — solar-pro $0.15/$0.6, gpt-5-mini $0.25/$2.00, claude-haiku-4-5 $1/$5
#   MID  — solar-pro(동일, 위 참고), gpt-5.4 $2.50/$15, claude-sonnet-5 $3/$15
#   HIGH — solar-pro(동일, 위 참고), gpt-5.5 $5/$30, claude-opus-5 $5/$25
# openai/upstage 모델 ID는 가격만 실측했고 이 프로젝트의 structured_llm.call_structured()
# 경로(client.beta.chat.completions.parse())로 실제 호출은 아직 안 해봤다 —
# 붙이기 전에 작은 스크립트로 한 번 찔러볼 것(백엔드 CLAUDE.md "Structured output" 절 참고).
MODELS: dict[str, dict[ModelTier, str]] = {
    "anthropic": {
        ModelTier.LOW: "claude-haiku-4-5-20251001",
        ModelTier.MID: "claude-sonnet-5",
        ModelTier.HIGH: "claude-opus-5",
    },
    "openai": {
        ModelTier.LOW: "gpt-5-mini",
        ModelTier.MID: "gpt-5.4",
        ModelTier.HIGH: "gpt-5.5",
    },
    "upstage": {
        # solar-mini는 Step1 골든셋에서 탈락(few-shot 베끼기·태그 중복, 2026-08-07)
        # 확인된 모델이라 LOW에서 뺐다. Upstage는 solar-pro보다 위 단계가 없어
        # MID/HIGH도 그대로 solar-pro — 상위 모델이 별도로 나오면 분리.
        # 2026-09-11 할인가 종료 뒤 solar-pro2로 교체 예정.
        ModelTier.LOW: "solar-pro4",
        ModelTier.MID: "solar-pro4",
        ModelTier.HIGH: "solar-pro4",
    },
    "google": {
        # 미실측(위 2026-08-17 변경사항 참고) — 가격이 아니라 구글이 공개한 크기
        # 순서로만 배정. 2.5가 아니라 3세대로 지정(2026-08-17, 사용자 요청) — 3세대
        # 모델 ID 문자열 자체도 공개 문서 기준 추정이라, 실제 키로 찔러볼 때 구글
        # 콘솔의 정확한 모델 이름부터 다시 확인할 것. 가격도 아직 안 넣음(실측
        # 전엔 틀린 숫자를 주석에 박아두는 게 더 위험하다고 판단).
        ModelTier.LOW: "gemini-3-flash-lite",
        ModelTier.MID: "gemini-3-flash",
        ModelTier.HIGH: "gemini-3-pro",
    },
}


def get_model(provider: str, tier: ModelTier) -> str:
    """provider·tier 조합에 맞는 모델 ID를 반환한다. 등록 안 된 조합이면 ValueError."""
    try:
        return MODELS[provider][tier]
    except KeyError as exc:
        raise ValueError(f"모델 설정이 없습니다: provider={provider}, tier={tier}") from exc
