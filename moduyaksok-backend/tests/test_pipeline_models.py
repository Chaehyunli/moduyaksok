# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : app/pipeline/models.py의 provider·티어별 모델 설정 테스트
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
import pytest

from app.pipeline.models import MODELS, ModelTier, get_model

_PROVIDERS = ("anthropic", "openai", "upstage")


@pytest.mark.parametrize("provider", _PROVIDERS)
@pytest.mark.parametrize("tier", list(ModelTier))
def test_get_model_returns_string_for_every_provider_and_tier(provider, tier):
    model = get_model(provider, tier)
    assert isinstance(model, str)
    assert model


@pytest.mark.parametrize("provider", _PROVIDERS)
def test_every_provider_defines_all_tiers(provider):
    assert set(MODELS[provider].keys()) == set(ModelTier)


def test_get_model_unknown_provider_raises():
    with pytest.raises(ValueError, match="모델 설정이 없습니다"):
        get_model("unknown", ModelTier.LOW)
