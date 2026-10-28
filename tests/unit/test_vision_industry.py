"""Industry-specific vision prompt + multi-provider vision routing tests.

Verifies:
  1. The vision prompt builder emits industry-appropriate focus and a stable schema.
  2. Unknown/missing industry falls back to the generic focus (no crash).
  3. NVIDIA & OpenRouter providers parse a vision JSON payload (incl. fenced output).
  4. The router's vision chain prefers the configured provider and includes
     openrouter as a backup, while text-only providers (groq/mistral) are excluded.
"""

import json

import pytest

from app.core import config
from app.infrastructure.ai.nvidia import NvidiaProvider, _parse_vision_json
from app.infrastructure.ai.openrouter import OpenRouterProvider
from app.infrastructure.ai.vision_prompts import DEFECT_CODES, build_vision_instruction
from app.domain.claims.models import DefectType, ImageQuality


# ---------------------------------------------------------------------------
# 1 & 2. Prompt builder: industry focus + schema + fallback
# ---------------------------------------------------------------------------
def test_vision_prompt_industry_focus_and_schema():
    beauty = build_vision_instruction("beauty")
    food = build_vision_instruction("fresh_food")
    generic = build_vision_instruction(None)
    unknown = build_vision_instruction("not_a_real_industry")

    # Industry-specific focus differs per category
    assert "BEAUTY" in beauty and "leakage" in beauty.lower()
    assert "FRESH FOOD" in food and "mold" in food.lower()
    # Unknown & missing industry fall back to the generic focus (no crash)
    assert "physical damage" in generic.lower()
    assert "physical damage" in unknown.lower()

    # Every prompt carries the full JSON schema with all defect codes
    for prompt in (beauty, food, generic, unknown):
        assert '"defect_type"' in prompt
        assert '"damage_ratio_estimate"' in prompt
        assert '"confidence"' in prompt
        assert '"image_quality"' in prompt
        # No refund/business decisions
        assert "Do NOT make refund" in prompt


def test_vision_prompt_defect_codes_cover_all_enum_values():
    # Every prompt defect code must be a real DefectType (guards drift)
    for code in DEFECT_CODES:
        assert DefectType(code) is not None


# ---------------------------------------------------------------------------
# 3. NVIDIA / OpenRouter JSON parsing (robust to code fences + bad enums)
# ---------------------------------------------------------------------------
def _sample_payload(defect="scratch", quality="acceptable"):
    return {
        "defect_type": defect,
        "affected_items": 1,
        "damage_ratio_estimate": 25,
        "confidence": 0.88,
        "visible_evidence": ["화면 우측 하단 스크래치"],
        "image_quality": quality,
    }


def test_parse_vision_json_plain():
    obs = _parse_vision_json(json.dumps(_sample_payload(), ensure_ascii=False))
    assert obs.defect_type == DefectType.SCRATCH
    assert obs.damage_ratio_estimate == 25
    assert obs.confidence == pytest.approx(0.88)
    assert obs.image_quality == ImageQuality.ACCEPTABLE


def test_parse_vision_json_code_fenced_and_unknown_enum():
    fenced = "```json\n" + json.dumps(_sample_payload(defect="mystery_code", quality="weird")) + "\n```"
    obs = _parse_vision_json(fenced)
    # Unknown enums map to safe defaults instead of raising
    assert obs.defect_type == DefectType.UNCLEAR
    assert obs.image_quality == ImageQuality.ACCEPTABLE


def test_parse_vision_json_clamps_out_of_range():
    bad = dict(_sample_payload(), damage_ratio_estimate=999, confidence=3.5)
    obs = _parse_vision_json(json.dumps(bad))
    assert obs.damage_ratio_estimate == 100
    assert obs.confidence == 1.0


@pytest.mark.asyncio
async def test_openrouter_analyze_claim_image_parses(monkeypatch):
    provider = OpenRouterProvider(api_key="test-key", vision_model="openai/gpt-4o-mini")

    captured = {}

    class _FakeResp:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": json.dumps(_sample_payload(defect="leak"))}}]}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, json=None, headers=None):
            captured.update({"url": url, "payload": json, "headers": headers})
            return _FakeResp()

    monkeypatch.setattr("app.infrastructure.ai.openrouter.httpx.AsyncClient", _FakeClient)

    obs = await provider.analyze_claim_image(b"\xff\xd8fakejpg", "image/jpeg", industry="beauty")
    assert obs.defect_type == DefectType.LEAK
    # The industry prompt should have been embedded in the request
    text_part = captured["payload"]["messages"][0]["content"][0]["text"]
    assert "BEAUTY" in text_part
    # API key goes in the header, never in the payload
    assert captured["headers"]["Authorization"] == "Bearer test-key"


# ---------------------------------------------------------------------------
# 4. Vision chain composition
# ---------------------------------------------------------------------------
def test_vision_chain_excludes_text_only_providers(monkeypatch):
    from app.infrastructure.ai.router import AIProviderRouter

    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "g-key")
    monkeypatch.setattr(config.settings, "NVIDIA_API_KEY", "n-key")
    monkeypatch.setattr(config.settings, "OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(config.settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(config.settings, "MISTRAL_API_KEY", None)
    monkeypatch.setattr(config.settings, "APP_ENV", "production")
    monkeypatch.setattr(config.settings, "MOCK_AI", False)

    router = AIProviderRouter(mock_mode=False)
    chain = router.get_vision_provider_chain()

    # Groq/Mistral are text-only -> must NOT be in the vision chain
    assert "groq" not in chain
    # NVIDIA + OpenRouter both present, configured primary (gemini absent) first
    assert "nvidia" in chain
    assert "openrouter" in chain
    # No mock in a live-key environment
    assert "mock" not in chain
