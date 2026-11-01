import json
import socket
from urllib.error import URLError

import pytest

from core.cloud_model_client import (
    AuthenticationError,
    CloudModelClient,
    CloudModelError,
    CloudTimeoutError,
    InvalidModelError,
    ProviderUnavailableError,
    RateLimitError,
)


def _success_body(text="hello from cloud", model="openai/gpt-4o-mini"):
    return json.dumps(
        {
            "id": "gen-1",
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": text}}],
        }
    )


def test_complete_returns_message_text():
    captured = {}

    def transport(method, url, headers, body, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = dict(headers)
        captured["body"] = json.loads(body.decode("utf-8"))
        captured["timeout"] = timeout
        return 200, {"Content-Type": "application/json"}, _success_body()

    client = CloudModelClient(
        api_key="sk-or-test-key-1234567890",
        model="openai/gpt-4o-mini",
        transport=transport,
    )
    result = client.complete([{"role": "user", "content": "hi"}])

    assert result.text == "hello from cloud"
    assert result.model == "openai/gpt-4o-mini"
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"]["model"] == "openai/gpt-4o-mini"
    assert captured["headers"]["Authorization"].startswith("Bearer ")
    assert "sk-or-test-key-1234567890" in captured["headers"]["Authorization"]


def test_missing_api_key_raises_before_network():
    def transport(*_args, **_kwargs):
        raise AssertionError("network should not be called")

    client = CloudModelClient(api_key="x", model="openai/gpt-4o-mini", transport=transport)
    with pytest.raises(AuthenticationError):
        client.complete([{"role": "user", "content": "hi"}])


def test_empty_model_raises_invalid_model():
    client = CloudModelClient(
        api_key="sk-or-test-key-1234567890",
        model="   ",
        transport=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")),
    )
    with pytest.raises(InvalidModelError):
        client.complete([{"role": "user", "content": "hi"}])


@pytest.mark.parametrize(
    "status,body,error_cls",
    [
        (401, json.dumps({"error": {"message": "User not found."}}), AuthenticationError),
        (403, json.dumps({"error": {"message": "Forbidden"}}), AuthenticationError),
        (429, json.dumps({"error": {"message": "Rate limit exceeded"}}), RateLimitError),
        (503, json.dumps({"error": {"message": "Overloaded"}}), ProviderUnavailableError),
        (408, json.dumps({"error": {"message": "Timeout"}}), CloudTimeoutError),
        (
            400,
            json.dumps({"error": {"message": "openai/not-a-real-model is not a valid model ID"}}),
            InvalidModelError,
        ),
        (400, "", AuthenticationError),
    ],
)
def test_status_codes_map_to_typed_errors(status, body, error_cls):
    client = CloudModelClient(
        api_key="sk-or-test-key-1234567890",
        model="openai/gpt-4o-mini",
        transport=lambda *a, **k: (status, {}, body),
    )
    with pytest.raises(error_cls) as info:
        client.complete([{"role": "user", "content": "hi"}])
    assert info.value.status_code == status


def test_timeout_from_transport():
    def transport(*_args, **_kwargs):
        raise TimeoutError("timed out")

    client = CloudModelClient(
        api_key="sk-or-test-key-1234567890",
        model="openai/gpt-4o-mini",
        transport=transport,
    )
    with pytest.raises(CloudTimeoutError):
        client.complete([{"role": "user", "content": "hi"}])


def test_provider_unreachable():
    def transport(*_args, **_kwargs):
        raise URLError(socket.gaierror("name or service not known"))

    client = CloudModelClient(
        api_key="sk-or-test-key-1234567890",
        model="openai/gpt-4o-mini",
        transport=transport,
    )
    with pytest.raises(ProviderUnavailableError):
        client.complete([{"role": "user", "content": "hi"}])


def test_generic_400_is_invalid_request():
    client = CloudModelClient(
        api_key="sk-or-test-key-1234567890",
        model="openai/gpt-4o-mini",
        transport=lambda *a, **k: (
            400,
            {},
            json.dumps({"error": {"message": "messages is required"}}),
        ),
    )
    with pytest.raises(CloudModelError) as info:
        client.complete([{"role": "user", "content": "hi"}])
    assert info.value.error_type == "invalid_request"
