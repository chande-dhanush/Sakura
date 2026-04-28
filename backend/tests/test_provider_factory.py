import sys
from types import SimpleNamespace

import pytest

sys.modules.setdefault("speech_recognition", SimpleNamespace())
sys.modules.setdefault("pygame", SimpleNamespace())

from sakura_assistant.core.infrastructure.container import Container, LLMConfig
from sakura_assistant.core.execution.verifier import PlanVerifier


def test_auto_provider_prefers_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    cfg = LLMConfig()
    c = Container(config=cfg)
    assert c._resolve_stage_provider("router") == "groq"


def test_deepseek_planner_requires_explicit_model(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk_test")
    cfg = LLMConfig(planner_provider="deepseek", planner_model="")
    c = Container(config=cfg)
    with pytest.raises(RuntimeError):
        c._build_provider_llm("deepseek", "", 0.1, "planner")


@pytest.mark.asyncio
async def test_verifier_is_provider_agnostic():
    class FakeLLM:
        async def ainvoke(self, _messages):
            class R:
                content = '{"verdict":"PASS","reason":"ok"}'
            return R()

    verifier = PlanVerifier(FakeLLM())
    result = await verifier.averify("test", [{"tool": "web_search", "args": {}}], "ok")
    assert result["verdict"] == "PASS"
