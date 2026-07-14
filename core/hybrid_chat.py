import hashlib
import json
import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass

from django.core.cache import cache

from core.chat_intent import (
    INTENT_INSTRUCTIONS,
    ChatIntent,
    detect_intent,
    extract_model_phrases,
    resolve_phones,
)
from core.chat_perf import PipelineTiming, StageTimer, log_timing
from core.llm import generate_chat_reply, stream_chat_reply

from whatmobile.discontinued import is_whatmobile_phone_discontinued
from whatmobile.models import WhatMobilePhone
from whatmobile.spec_fallback import flatten_phone_specifications
from whatmobile.utils import normalize_price_to_pkr

logger = logging.getLogger(__name__)

NOT_FOUND_REPLY = (
    "I'm sorry, I couldn't find this mobile phone in the WhatMobile database."
)

WELCOME_MESSAGE = (
    "Welcome to PriceVerse Phone Assistant.\n\n"
    "I can help you compare phones, check prices and specs, give recommendations, "
    "and answer buying questions using the latest WhatMobile data.\n\n"
    "Try asking: *Which phone is better, iPhone 12 or Samsung Galaxy S22?*"
)

SYSTEM_PROMPT = (
    "You are PriceVerse phone assistant. Answer using ONLY the DATABASE JSON provided. "
    "Reply in the user's language (English, Urdu, or Roman Urdu). "
    "Use concise Markdown (headings, bullets, tables for comparisons). "
    "Never invent specs or prices. Compare only the phones given. Be brief."
)

CACHE_TTL = 300
PHONE_SERIAL_CACHE_TTL = 3600
CATALOG_VERSION_TTL = 120

LLM_MAX_PHONES = 4
LLM_MAX_SPECS = 12
LLM_MAX_SPEC_VALUE = 80
LLM_MAX_DESC = 120

INTENT_MAX_TOKENS: dict[str, int] = {
    "compare_models": 380,
    "compare_brands": 420,
    "single_phone": 280,
    "worth_buying": 320,
    "recommend": 400,
    "feature_focus": 320,
    "pros_cons": 300,
    "general": 300,
}

# Priority specs sent to the model (reduces prompt size).
_PRIORITY_SPEC_KEYS = (
    "display",
    "screen",
    "processor",
    "chipset",
    "ram",
    "storage",
    "battery",
    "camera",
    "main camera",
    "front camera",
    "os",
    "weight",
    "dimensions",
)

GREETING_WORDS = {
    "hi", "hii", "hiya", "hey", "heya", "hello", "helo", "hellow",
    "yo", "hye", "assalam", "assalamualaikum", "salam", "salaam", "aoa",
    "alaikum", "alaykum", "walaikum", "waalaikum", "greetings", "welcome",
}
GREETING_FILLER_WORDS = {
    "there", "everyone", "team", "good", "morning", "evening", "afternoon",
    "day", "sir", "maam", "madam", "please", "dear", "bot", "assistant",
    "a", "o", "wa", "and",
}


@dataclass
class ChatResponse:
    text: str
    timing: PipelineTiming


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _cache_key(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.md5(value.encode('utf-8')).hexdigest()}"


def _catalog_version() -> int:
    cached = cache.get("wm:catalog_version")
    if cached is not None:
        return int(cached)
    latest = (
        WhatMobilePhone.objects.using("whatmobile")
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    version = int(latest.timestamp()) if latest else 0
    cache.set("wm:catalog_version", version, CATALOG_VERSION_TTL)
    return version


def _is_greeting(text: str) -> bool:
    tokens = re.findall(r"[a-z]+", _normalize(text))
    if not tokens:
        return False
    if not any(tok in GREETING_WORDS for tok in tokens):
        return False
    return all(tok in GREETING_WORDS or tok in GREETING_FILLER_WORDS for tok in tokens)


def _trim_specs(specs: dict, intent_kind: str) -> dict:
    if not specs:
        return {}
    trimmed: dict = {}
    lower_map = {str(k).lower(): v for k, v in specs.items() if v not in (None, "")}

    for key in _PRIORITY_SPEC_KEYS:
        if len(trimmed) >= LLM_MAX_SPECS:
            break
        for spec_key, value in lower_map.items():
            if key in spec_key and spec_key not in trimmed:
                text = str(value)
                if len(text) > LLM_MAX_SPEC_VALUE:
                    text = text[: LLM_MAX_SPEC_VALUE - 3] + "..."
                trimmed[spec_key] = text
                break

    if intent_kind in {"compare_models", "compare_brands"} and len(trimmed) < LLM_MAX_SPECS:
        for spec_key, value in lower_map.items():
            if len(trimmed) >= LLM_MAX_SPECS:
                break
            if spec_key in trimmed:
                continue
            text = str(value)
            if len(text) > LLM_MAX_SPEC_VALUE:
                text = text[: LLM_MAX_SPEC_VALUE - 3] + "..."
            trimmed[spec_key] = text

    return trimmed


def _lite_price(phone: WhatMobilePhone) -> tuple[int | None, str]:
    pkr_value, _ = normalize_price_to_pkr(
        phone.official_price,
        phone.official_price_value,
        phone.official_price_currency,
    )
    return pkr_value, phone.official_price or ""


def serialize_phone(phone: WhatMobilePhone, intent_kind: str = "general") -> dict:
    cache_key = f"phone-ser:{phone.id}:{phone.updated_at.timestamp() if phone.updated_at else 0}:{intent_kind}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    specs = flatten_phone_specifications(phone)
    price_pkr, official_text = _lite_price(phone)
    discontinued = is_whatmobile_phone_discontinued(phone)

    data = {
        "model": phone.model_name,
        "brand": phone.get_brand_display(),
        "price_pkr": price_pkr,
        "price_text": official_text,
        "status": phone.release_status or "",
        "discontinued": discontinued,
        "specs": _trim_specs(specs, intent_kind),
    }
    if intent_kind in {"single_phone", "worth_buying", "pros_cons"}:
        desc = (phone.description or "")[:LLM_MAX_DESC]
        if desc:
            data["summary"] = desc

    cache.set(cache_key, data, PHONE_SERIAL_CACHE_TTL)
    return data


def build_llm_payload(phones: list[WhatMobilePhone], intent_kind: str = "general") -> str:
    payload = []
    for phone in phones[:LLM_MAX_PHONES]:
        try:
            payload.append(serialize_phone(phone, intent_kind=intent_kind))
        except (AttributeError, TypeError):
            continue
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _build_user_prompt(intent: ChatIntent, database_json: str, message: str) -> str:
    instruction = INTENT_INSTRUCTIONS.get(intent.kind, INTENT_INSTRUCTIONS["general"])
    return (
        f"Task ({intent.kind}): {instruction}\n\n"
        f"DATABASE JSON:\n{database_json}\n\n"
        f"Question: {message}"
    )


def _format_price_markdown(price_pkr: int | None, official_text: str = "") -> str:
    if price_pkr and price_pkr > 0:
        return f"Rs. {price_pkr:,}"
    if official_text:
        return official_text
    return "Not available"


def _fallback_db_reply(intent: ChatIntent, phones: list[WhatMobilePhone]) -> str:
    if not phones:
        return NOT_FOUND_REPLY

    if intent.kind == "compare_models" and len(phones) >= 2:
        lines = ["## Quick Comparison", ""]
        lines.append("| Feature | " + " | ".join(p.model_name for p in phones[:2]) + " |")
        lines.append("| --- | " + " | ".join("---" for _ in phones[:2]) + " |")
        for label, key in (("Price", "price_pkr"), ("Brand", "brand")):
            row = [label]
            for phone in phones[:2]:
                data = serialize_phone(phone, intent_kind=intent.kind)
                val = data.get(key)
                if key == "price_pkr":
                    val = _format_price_markdown(val, data.get("price_text", ""))
                row.append(str(val or "—"))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
        lines.append(
            "_AI model was slow to respond, so this is a quick database summary. "
            "Try again for a full analysis._"
        )
        return "\n".join(lines)

    phone = phones[0]
    data = serialize_phone(phone, intent_kind=intent.kind)
    return (
        f"# {data['model']}\n\n"
        f"**Price:** {_format_price_markdown(data.get('price_pkr'), data.get('price_text', ''))}\n\n"
        "_Prices may vary by city or retailer._"
    )


def _prepare_context(
    message: str,
    history: list[dict] | None,
    timing: PipelineTiming,
) -> tuple[ChatIntent, list[WhatMobilePhone], str, str] | None:
    text = (message or "").strip()
    history = history or []

    if not text:
        return None

    with StageTimer(timing, "intent_ms"):
        if _is_greeting(text) and not history:
            return None
        intent = detect_intent(text, history=history)

    with StageTimer(timing, "db_ms"):
        phones = resolve_phones(intent)

    if not phones:
        return None

    timing.phone_count = len(phones)

    with StageTimer(timing, "payload_ms"):
        database_json = build_llm_payload(phones, intent_kind=intent.kind)
        user_prompt = _build_user_prompt(intent, database_json, text)

    return intent, phones, database_json, user_prompt


def _phones_not_found_reply(intent: ChatIntent, text: str) -> str:
    mentioned = extract_model_phrases(intent.context_message or text)
    if mentioned:
        return NOT_FOUND_REPLY
    if intent.kind in {"compare_brands", "recommend", "feature_focus", "general"}:
        return (
            "I could not find enough matching phones in the WhatMobile database for that question. "
            "Please mention a specific model or brand."
        )
    return NOT_FOUND_REPLY


def process_chat(
    message: str,
    history: list[dict] | None = None,
) -> ChatResponse:
    """Full chat pipeline with per-stage timing."""
    timing = PipelineTiming()
    t0 = time.perf_counter()
    text = (message or "").strip()
    history = history or []

    if not text:
        timing.total_ms = (time.perf_counter() - t0) * 1000
        return ChatResponse(text="Please type a message.", timing=timing)

    if _is_greeting(text) and not history:
        timing.total_ms = (time.perf_counter() - t0) * 1000
        timing.source = "welcome"
        return ChatResponse(text=WELCOME_MESSAGE, timing=timing)

    with StageTimer(timing, "intent_ms"):
        intent = detect_intent(text, history=history)

    cache_salt = json.dumps(
        [{"role": h.get("role"), "content": (h.get("content") or "")[:80]} for h in history[-2:]],
        ensure_ascii=False,
    )
    cache_token = _cache_key(
        f"wm-chat:{_catalog_version()}:{intent.kind}",
        _normalize(text) + cache_salt,
    )
    cached = cache.get(cache_token)
    if cached is not None:
        timing.cached = True
        timing.source = "cache"
        timing.total_ms = (time.perf_counter() - t0) * 1000
        log_timing(timing, intent.kind)
        return ChatResponse(text=cached, timing=timing)

    with StageTimer(timing, "db_ms"):
        phones = resolve_phones(intent)

    if not phones:
        timing.total_ms = (time.perf_counter() - t0) * 1000
        timing.source = "not_found"
        log_timing(timing, intent.kind)
        return ChatResponse(text=_phones_not_found_reply(intent, text), timing=timing)

    timing.phone_count = len(phones)

    with StageTimer(timing, "payload_ms"):
        database_json = build_llm_payload(phones, intent_kind=intent.kind)
        user_prompt = _build_user_prompt(intent, database_json, text)

    llm_t0 = time.perf_counter()
    max_tokens = INTENT_MAX_TOKENS.get(intent.kind, 300)
    result = generate_chat_reply(
        SYSTEM_PROMPT,
        user_prompt,
        database_json,
        history=history,
        num_predict=max_tokens,
    )
    timing.llm_ms = result.llm_ms or ((time.perf_counter() - llm_t0) * 1000)

    if result.ok:
        timing.source = result.source
        cache.set(cache_token, result.text, CACHE_TTL)
        timing.total_ms = (time.perf_counter() - t0) * 1000
        log_timing(timing, intent.kind)
        return ChatResponse(text=result.text, timing=timing)

    logger.warning(
        "Ollama/Llama unavailable (%s: %s) — using database fallback",
        result.source,
        result.error or "unknown",
    )
    timing.source = f"fallback:{result.source}"
    reply = _fallback_db_reply(intent, phones)
    timing.total_ms = (time.perf_counter() - t0) * 1000
    log_timing(timing, intent.kind)
    return ChatResponse(text=reply, timing=timing)


def stream_chat(
    message: str,
    history: list[dict] | None = None,
) -> Iterator[str | ChatResponse]:
    """
    Stream Ollama tokens. Yields str chunks, then a final ChatResponse.
    On cache hit or fallback, yields the full text once then ChatResponse.
    """
    timing = PipelineTiming()
    t0 = time.perf_counter()
    text = (message or "").strip()
    history = history or []

    if not text:
        timing.total_ms = (time.perf_counter() - t0) * 1000
        yield ChatResponse(text="Please type a message.", timing=timing)
        return

    if _is_greeting(text) and not history:
        timing.total_ms = (time.perf_counter() - t0) * 1000
        timing.source = "welcome"
        yield WELCOME_MESSAGE
        yield ChatResponse(text=WELCOME_MESSAGE, timing=timing)
        return

    with StageTimer(timing, "intent_ms"):
        intent = detect_intent(text, history=history)

    cache_salt = json.dumps(
        [{"role": h.get("role"), "content": (h.get("content") or "")[:80]} for h in history[-2:]],
        ensure_ascii=False,
    )
    cache_token = _cache_key(
        f"wm-chat:{_catalog_version()}:{intent.kind}",
        _normalize(text) + cache_salt,
    )
    cached = cache.get(cache_token)
    if cached is not None:
        timing.cached = True
        timing.source = "cache"
        timing.total_ms = (time.perf_counter() - t0) * 1000
        log_timing(timing, intent.kind)
        yield cached
        yield ChatResponse(text=cached, timing=timing)
        return

    with StageTimer(timing, "db_ms"):
        phones = resolve_phones(intent)

    if not phones:
        timing.total_ms = (time.perf_counter() - t0) * 1000
        timing.source = "not_found"
        reply = _phones_not_found_reply(intent, text)
        yield reply
        yield ChatResponse(text=reply, timing=timing)
        return

    timing.phone_count = len(phones)

    with StageTimer(timing, "payload_ms"):
        database_json = build_llm_payload(phones, intent_kind=intent.kind)
        user_prompt = _build_user_prompt(intent, database_json, text)

    llm_t0 = time.perf_counter()
    max_tokens = INTENT_MAX_TOKENS.get(intent.kind, 300)
    parts: list[str] = []
    for chunk in stream_chat_reply(
        SYSTEM_PROMPT,
        user_prompt,
        history=history,
        num_predict=max_tokens,
    ):
        parts.append(chunk)
        yield chunk

    timing.llm_ms = (time.perf_counter() - llm_t0) * 1000

    if parts:
        full_text = "".join(parts)
        timing.source = "ollama"
        cache.set(cache_token, full_text, CACHE_TTL)
        timing.total_ms = (time.perf_counter() - t0) * 1000
        log_timing(timing, intent.kind)
        yield ChatResponse(text=full_text, timing=timing)
        return

    logger.warning("Ollama stream empty — using database fallback")
    timing.source = "fallback:stream"
    reply = _fallback_db_reply(intent, phones)
    timing.total_ms = (time.perf_counter() - t0) * 1000
    log_timing(timing, intent.kind)
    yield reply
    yield ChatResponse(text=reply, timing=timing)


def get_hybrid_chat_reply(message: str, history: list[dict] | None = None) -> str:
    """Backward-compatible wrapper."""
    return process_chat(message, history=history).text
