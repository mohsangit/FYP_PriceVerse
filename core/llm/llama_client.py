"""Official Meta Llama / Ollama integration for the PriceVerse chatbot."""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None
_warmup_lock = threading.Lock()
_warmup_done = False

ReplySource = Literal["ollama", "llama_stack", "timeout", "error", "unavailable"]


@dataclass
class ChatReplyResult:
    text: str | None
    source: ReplySource
    error: str = ""
    llm_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return bool(self.text) and self.source in {"ollama", "llama_stack"}


def _stack_base_url() -> str:
    return (getattr(settings, "LLAMA_STACK_BASE_URL", "") or "http://localhost:8321").rstrip("/")


def _is_ollama() -> bool:
    return ":11434" in _stack_base_url()


def _model_id() -> str:
    return getattr(settings, "LLAMA_MODEL_ID", "Llama3.1-8B-Instruct")


def _max_tokens() -> int:
    return int(getattr(settings, "LLAMA_MAX_TOKENS", 500) or 500)


def _temperature() -> float:
    return float(getattr(settings, "LLAMA_TEMPERATURE", 0.2) or 0.2)


def _request_timeout() -> float:
    default = "120" if _is_ollama() else "90"
    return float(getattr(settings, "LLAMA_REQUEST_TIMEOUT", default) or default)


def _history_turns() -> int:
    return int(getattr(settings, "CHAT_LLM_HISTORY_TURNS", 4) or 4)


def _history_char_limit() -> int:
    return int(getattr(settings, "CHAT_LLM_HISTORY_CHARS", 200) or 200)


def _ollama_options(num_predict: int | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "temperature": _temperature(),
        "num_predict": num_predict or _max_tokens(),
    }
    keep_alive = getattr(settings, "LLAMA_KEEP_ALIVE", "30m")
    if keep_alive:
        return {"options": options, "keep_alive": keep_alive}
    return {"options": options}


def get_llama_client():
    """Return a cached Llama Stack client (official SDK when installed)."""
    global _client
    if _client is not None:
        return _client

    try:
        from llama_stack_client import LlamaStackClient
    except ImportError:
        _client = None
        return None

    _client = LlamaStackClient(
        base_url=_stack_base_url(),
        timeout=_request_timeout(),
    )
    return _client


def _extract_completion_text(body: dict[str, Any]) -> str | None:
    choices = body.get("choices") or []
    if not choices:
        return None

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    text = choices[0].get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    return None


def _trim_turn_content(content: str, max_len: int | None = None) -> str:
    limit = max_len if max_len is not None else _history_char_limit()
    text = (content or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            return True
        return "timed out" in str(exc).lower() or "timed out" in str(reason).lower()
    return False


def _build_messages(
    system_prompt: str,
    user_message: str,
    history: list[dict] | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in (history or [])[-_history_turns() :]:
        role = turn.get("role")
        content = _trim_turn_content(turn.get("content") or "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _build_payload(
    system_prompt: str,
    user_message: str,
    history: list[dict] | None,
    *,
    stream: bool,
    num_predict: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": _model_id(),
        "messages": _build_messages(system_prompt, user_message, history),
        "temperature": _temperature(),
        "max_tokens": num_predict or _max_tokens(),
        "stream": stream,
    }
    if _is_ollama():
        payload.update(_ollama_options(num_predict=num_predict))
    return payload


def warmup_ollama() -> bool:
    """Load the Ollama model once and keep it warm for subsequent requests."""
    global _warmup_done
    if not _is_ollama():
        return False
    with _warmup_lock:
        if _warmup_done:
            return True
        try:
            payload = _build_payload(
                "Reply OK only.",
                "OK",
                history=[],
                stream=False,
                num_predict=8,
            )
            request = urllib.request.Request(
                f"{_stack_base_url()}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                response.read()
            _warmup_done = True
            logger.info("Ollama model %s warmed up and kept alive", _model_id())
            return True
        except Exception as exc:
            logger.warning("Ollama warmup failed: %s", exc)
            return False


def _call_stack_http(
    system_prompt: str,
    user_message: str,
    history: list[dict] | None = None,
    num_predict: int | None = None,
) -> ChatReplyResult:
    import time

    payload = _build_payload(
        system_prompt,
        user_message,
        history,
        stream=False,
        num_predict=num_predict,
    )
    request = urllib.request.Request(
        f"{_stack_base_url()}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "PriceVerse-Django/1.0",
        },
        method="POST",
    )

    timeout = _request_timeout()
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = _extract_completion_text(body)
        llm_ms = (time.perf_counter() - t0) * 1000
        if text:
            source: ReplySource = "ollama" if _is_ollama() else "llama_stack"
            logger.info("Chat reply via %s (%d chars, %.0fms)", source, len(text), llm_ms)
            return ChatReplyResult(text=text, source=source, llm_ms=llm_ms)
        return ChatReplyResult(text=None, source="error", error="Empty model response", llm_ms=llm_ms)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error("Llama Stack HTTP error: %s", detail)
        return ChatReplyResult(text=None, source="error", error=detail[:300])
    except (TimeoutError, urllib.error.URLError) as exc:
        if not _is_timeout_error(exc):
            logger.error("Llama Stack request failed: %s", exc)
            return ChatReplyResult(text=None, source="unavailable", error=str(exc))
        logger.error("Llama/Ollama request timed out after %ss", timeout)
        return ChatReplyResult(text=None, source="timeout", error=f"timeout after {timeout}s")
    except (KeyError, json.JSONDecodeError) as exc:
        logger.error("Llama Stack response parse failed: %s", exc)
        return ChatReplyResult(text=None, source="error", error=str(exc))


def stream_chat_reply(
    system_prompt: str,
    user_message: str,
    history: list[dict] | None = None,
    num_predict: int | None = None,
) -> Iterator[str]:
    """Stream Ollama/Llama Stack tokens as they are generated."""
    if not _is_ollama():
        result = _call_stack_http(system_prompt, user_message, history, num_predict=num_predict)
        if result.text:
            yield result.text
        return

    payload = _build_payload(
        system_prompt,
        user_message,
        history,
        stream=True,
        num_predict=num_predict,
    )
    request = urllib.request.Request(
        f"{_stack_base_url()}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "PriceVerse-Django/1.0",
        },
        method="POST",
    )

    timeout = _request_timeout()
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except (TimeoutError, urllib.error.URLError) as exc:
        if _is_timeout_error(exc):
            logger.error("Ollama stream timed out after %ss", timeout)
        else:
            logger.error("Ollama stream failed: %s", exc)
        return

    try:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                yield content
    finally:
        response.close()


def _call_stack_sdk(
    system_prompt: str,
    user_message: str,
    history: list[dict] | None = None,
) -> ChatReplyResult:
    client = get_llama_client()
    if client is None:
        return ChatReplyResult(text=None, source="unavailable", error="SDK not installed")

    messages = _build_messages(system_prompt, user_message, history)

    try:
        if hasattr(client, "chat") and hasattr(client.chat, "completions"):
            completion = client.chat.completions.create(
                model=_model_id(),
                messages=messages,
                temperature=_temperature(),
                max_tokens=_max_tokens(),
            )
            if hasattr(completion, "choices") and completion.choices:
                message = completion.choices[0].message
                content = getattr(message, "content", None) or message.get("content")
                if content:
                    text = str(content).strip()
                    logger.info("Chat reply generated via llama_stack SDK (%d chars)", len(text))
                    return ChatReplyResult(text=text, source="llama_stack")
            return ChatReplyResult(text=None, source="error", error="Empty SDK response")

        completion = client.inference.chat_completion(
            model_id=_model_id(),
            messages=messages,
            params={"temperature": _temperature(), "max_tokens": _max_tokens()},
        )
        content = getattr(completion, "completion_message", None)
        if content is not None:
            text = getattr(content, "content", None)
            if text:
                return ChatReplyResult(text=str(text).strip(), source="llama_stack")
        if isinstance(completion, dict):
            text = _extract_completion_text(completion)
            if text:
                return ChatReplyResult(text=text, source="llama_stack")
    except Exception as exc:
        logger.error("Llama Stack SDK request failed: %s", exc)
        return ChatReplyResult(text=None, source="error", error=str(exc))

    return ChatReplyResult(text=None, source="error", error="SDK returned no content")


def generate_chat_reply(
    system_prompt: str,
    user_message: str,
    database_json: str,
    history: list[dict] | None = None,
    num_predict: int | None = None,
) -> ChatReplyResult:
    """Generate a chat reply with Ollama or Llama Stack."""
    _ = database_json  # embedded in user_message by hybrid_chat

    if _is_ollama():
        return _call_stack_http(
            system_prompt,
            user_message,
            history=history,
            num_predict=num_predict,
        )

    sdk_result = _call_stack_sdk(system_prompt, user_message, history=history)
    if sdk_result.ok:
        return sdk_result
    http_result = _call_stack_http(system_prompt, user_message, history=history)
    return http_result if http_result.ok else sdk_result
