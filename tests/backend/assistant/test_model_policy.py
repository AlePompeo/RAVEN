# SPDX-License-Identifier: Apache-2.0
import pytest

from backend.assistant.cloud import MODEL_RE, groq_config, model_allowed


@pytest.mark.parametrize(
    "name",
    [
        "qwen3-32b",
        "Qwen/Qwen2.5-7B-Instruct",
        "openai/qwen-3",
        "deepseek-r1-distill-llama-70b",
        "DeepSeek-V3",
        "moonshotai/kimi-k2",
        "zai-org/GLM-4.5",
        "z-ai/glm-4",
        "glm-4.6",
        "01-ai/Yi-1.5-9B",
        "yi-large",
        "internlm2_5-7b",
        "baichuan2-13b",
        "minimax-m2",
        "ernie-4.5",
        "tencent/hunyuan-a13b",
        "alibaba/anything",
        "ai-sage/GigaChat-20B",
        "yandex/YandexGPT-5",
        "sberbank-ai/rugpt3",
        "bytedance/doubao-1.5",
    ],
)
def test_models_of_chinese_or_russian_organisations_are_refused(name: str) -> None:
    assert not model_allowed(name) and MODEL_RE.match(name) is None


@pytest.mark.parametrize(
    "name",
    [
        "openai/gpt-oss-20b",
        "gpt-4o-mini",
        "claude-sonnet-5-5",
        "ibm-granite/granite-4.0-1b",
        "granite-4.0-h-350m",
        "microsoft/Phi-4-mini-instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "HuggingFaceTB/SmolLM3-3B",
        "allenai/OLMo-2-1124-7B",
        "llama-3.3-70b",
        "gemma-3-4b",
        "yield-model-1",
    ],
)
def test_western_models_pass_and_look_alikes_are_not_caught(name: str) -> None:
    assert model_allowed(name)


def test_the_shape_rule_still_applies_and_the_cloud_config_refuses_a_denied_model() -> None:
    assert not model_allowed("bad name with spaces") and not model_allowed("")
    env = {"RAVEN_SI_CLOUD_ENABLED": "1", "GROQ_API_KEY": "k", "GROQ_MODEL": "qwen/qwen3-32b"}
    assert groq_config(env) is None  # a Western host serving a denied model is still refused
    assert groq_config({**env, "GROQ_MODEL": "openai/gpt-oss-20b"}) is not None


def test_the_chat_route_refuses_a_denied_model_even_from_a_western_provider() -> None:
    from fastapi.testclient import TestClient

    from backend.bootstrap import build_app

    c = TestClient(build_app())
    body = {
        "messages": [{"role": "user", "content": "ciao"}],
        "provider": "groq",
        "model": "qwen/qwen3-32b",
        "allow_external": True,
    }
    r = c.post("/api/assistant/chat", json=body)
    assert r.status_code == 422 and "qwen" not in r.text.lower()
