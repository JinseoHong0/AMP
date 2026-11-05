import asyncio
import json

import httpx
import pytest
from google import genai

from backend.config import Settings
from backend.errors import ApiError
from backend.services.llm import GeminiPosterClient


def use_transport(monkeypatch, handler):
    # Exercise the actual SDK serialization without a live key, network or billable request.
    real_client = genai.Client

    def client(**kwargs):
        kwargs["http_options"].async_client_args = {"transport": httpx.MockTransport(handler)}
        return real_client(**kwargs)

    monkeypatch.setattr(genai, "Client", client)


def settings(**changes):
    return Settings(
        _env_file=None, gemini_api_key="test-only", gemini_model="test-vision-model", **changes
    )


def test_gemini_image_and_schema_request(monkeypatch, vision_result, image_bytes):
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "role": "model",
                            "parts": [{"text": vision_result.model_dump_json()}],
                        },
                    }
                ]
            },
        )

    use_transport(monkeypatch, respond)
    result = asyncio.run(GeminiPosterClient(settings()).extract(image_bytes(), "image/png"))
    assert result == vision_result
    assert len(captured) == 1
    body = captured[0]
    assert body["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/png"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "venue_id" not in json.dumps(body["generationConfig"]["responseJsonSchema"])
    assert "untrusted data" in body["systemInstruction"]["parts"][0]["text"]
    assert "tools" not in body


@pytest.mark.parametrize(
    "status,payload",
    [
        (
            429,
            {
                "error": {
                    "code": 429,
                    "message": "provider-private-details",
                    "status": "RESOURCE_EXHAUSTED",
                }
            },
        ),
        (200, {"candidates": [{"finishReason": "SAFETY"}]}),
        (200, {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
        (
            200,
            {
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}
                ]
            },
        ),
    ],
)
def test_ai_failures_are_safe_and_not_retried(monkeypatch, status, payload):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, json=payload)

    use_transport(monkeypatch, respond)
    with pytest.raises(ApiError) as error:
        asyncio.run(GeminiPosterClient(settings()).extract(b"image", "image/png"))
    assert error.value.status == 503
    assert error.value.code == "AI_UNAVAILABLE"
    assert "provider-private-details" not in error.value.message
    assert len(calls) == 1


def test_timeout_and_no_key(monkeypatch):
    async def slow(_request):
        await asyncio.sleep(1)
        return httpx.Response(500)

    use_transport(monkeypatch, slow)
    with pytest.raises(ApiError):
        asyncio.run(
            GeminiPosterClient(settings(ai_poster_timeout_seconds=0.05)).extract(
                b"image", "image/png"
            )
        )
    with pytest.raises(ApiError) as error:
        asyncio.run(
            GeminiPosterClient(
                Settings(_env_file=None, gemini_api_key="", gemini_model="")
            ).extract(b"image", "image/png")
        )
    assert error.value.code == "AI_UNAVAILABLE"
