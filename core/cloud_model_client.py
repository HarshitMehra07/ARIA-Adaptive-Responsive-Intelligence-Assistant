from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import settings


class CloudModelError(Exception):
    """Base error for cloud model requests."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        error_type: str = "cloud_model_error",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


class AuthenticationError(CloudModelError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code, error_type="authentication_error")


class InvalidModelError(CloudModelError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code, error_type="invalid_model")


class RateLimitError(CloudModelError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code, error_type="rate_limit")


class CloudTimeoutError(CloudModelError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code, error_type="timeout")


class ProviderUnavailableError(CloudModelError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code, error_type="provider_unavailable")


@dataclass
class CloudModelResponse:
    text: str
    model: str
    raw: Dict[str, Any]


TransportResponse = tuple[int, Mapping[str, str], str]
Transport = Callable[[str, str, Mapping[str, str], Optional[bytes], float], TransportResponse]


def _default_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: Optional[bytes],
    timeout: float,
) -> TransportResponse:
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return int(response.status), dict(response.headers.items()), raw
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        return int(error.code), dict(error.headers.items()), raw


def _extract_error_message(body: str) -> str:
    if not body or not body.strip():
        return ""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:500]

    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("metadata", {}).get("raw")
        if message:
            return str(message)
        return json.dumps(error)[:500]
    if isinstance(error, str):
        return error
    if payload.get("message"):
        return str(payload["message"])
    return body.strip()[:500]


def _looks_like_invalid_model(message: str, model: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "not a valid model",
            "invalid model",
            "model not found",
            "no such model",
            "is not available",
            "unknown model",
        )
    ) or (model and model.lower() in lowered and "model" in lowered)


class CloudModelClient:
    """OpenRouter-compatible chat completions client."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = settings.DEFAULT_OPENROUTER_BASE_URL,
        timeout_seconds: float = settings.DEFAULT_OPENROUTER_TIMEOUT_SECONDS,
        http_referer: str = settings.OPENROUTER_HTTP_REFERER,
        app_title: str = settings.OPENROUTER_APP_TITLE,
        transport: Optional[Transport] = None,
    ):
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.base_url = (base_url or settings.DEFAULT_OPENROUTER_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_referer = http_referer
        self.app_title = app_title
        self.transport = transport or _default_transport

    @classmethod
    def from_env(cls, transport: Optional[Transport] = None) -> "CloudModelClient":
        return cls(
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_MODEL,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout_seconds=settings.OPENROUTER_TIMEOUT_SECONDS,
            http_referer=settings.OPENROUTER_HTTP_REFERER,
            app_title=settings.OPENROUTER_APP_TITLE,
            transport=transport,
        )

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> CloudModelResponse:
        chosen_model = (model or self.model).strip()
        self._validate_configuration(chosen_model)

        payload: Dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.http_referer,
            "X-Title": self.app_title,
        }
        body = json.dumps(payload).encode("utf-8")

        try:
            status, response_headers, raw_body = self.transport(
                "POST",
                url,
                headers,
                body,
                self.timeout_seconds,
            )
        except TimeoutError as error:
            raise CloudTimeoutError(f"The cloud model request timed out: {error}") from error
        except socket.timeout as error:
            raise CloudTimeoutError(f"The cloud model request timed out: {error}") from error
        except URLError as error:
            reason = str(getattr(error, "reason", error))
            lowered = reason.lower()
            if "timed out" in lowered or "timeout" in lowered:
                raise CloudTimeoutError("The cloud model request timed out.") from error
            raise ProviderUnavailableError(
                f"The cloud model provider could not be reached: {reason}"
            ) from error
        except OSError as error:
            raise ProviderUnavailableError(
                f"The cloud model provider could not be reached: {error}"
            ) from error

        return self._parse_response(
            status=status,
            response_headers=response_headers,
            raw_body=raw_body,
            model=chosen_model,
        )

    def _validate_configuration(self, model: str) -> None:
        if not self.api_key or len(self.api_key) < settings.MIN_API_KEY_LENGTH:
            raise AuthenticationError(
                "OPENROUTER_API_KEY is missing or invalid. "
                "Set a full OpenRouter key in the local .env file."
            )
        if not model:
            raise InvalidModelError(
                "No cloud model ID is configured. Set OPENROUTER_MODEL in the local .env file."
            )

    def _parse_response(
        self,
        *,
        status: int,
        response_headers: Mapping[str, str],
        raw_body: str,
        model: str,
    ) -> CloudModelResponse:
        del response_headers  # kept out of logs; callers should not print secrets

        if status == 200:
            try:
                payload = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError as error:
                raise CloudModelError(
                    "The cloud model returned an unreadable success response.",
                    status_code=status,
                ) from error
            text = self._extract_text(payload)
            used_model = payload.get("model") or model
            return CloudModelResponse(text=text, model=used_model, raw=payload)

        message = _extract_error_message(raw_body)
        raise self._error_for_status(status, message, model)

    def _error_for_status(self, status: int, message: str, model: str) -> CloudModelError:
        detail = message or "empty response body"
        if status in (401, 403):
            return AuthenticationError(
                f"OpenRouter authentication failed ({status}): {detail}",
                status_code=status,
            )
        if status == 429:
            return RateLimitError(
                f"OpenRouter rate limit reached ({status}): {detail}",
                status_code=status,
            )
        if status in (408, 504):
            return CloudTimeoutError(
                f"The cloud model request timed out ({status}): {detail}",
                status_code=status,
            )
        if status in (502, 503, 522, 524):
            return ProviderUnavailableError(
                f"The cloud model provider is unavailable ({status}): {detail}",
                status_code=status,
            )
        if status == 404 or _looks_like_invalid_model(message, model):
            return InvalidModelError(
                f"The configured model '{model}' is invalid or unavailable ({status}): {detail}",
                status_code=status,
            )
        if status == 400:
            lowered = detail.lower()
            if "key" in lowered or "auth" in lowered or "unauthorized" in lowered:
                return AuthenticationError(
                    f"OpenRouter rejected the API key ({status}): {detail}",
                    status_code=status,
                )
            if detail == "empty response body":
                return AuthenticationError(
                    "OpenRouter returned HTTP 400 with an empty body. "
                    "This usually means the API key is missing, truncated, or rejected at the edge.",
                    status_code=status,
                )
            return CloudModelError(
                f"OpenRouter rejected the request ({status}): {detail}",
                status_code=status,
                error_type="invalid_request",
            )
        return CloudModelError(
            f"OpenRouter request failed ({status}): {detail}",
            status_code=status,
        )

    @staticmethod
    def _extract_text(payload: Dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise CloudModelError("The cloud model returned no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
                elif isinstance(item, str):
                    parts.append(item)
            content = "".join(parts)
        if not content:
            raise CloudModelError("The cloud model returned an empty message.")
        return str(content).strip()
