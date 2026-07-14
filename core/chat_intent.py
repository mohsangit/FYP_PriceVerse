"""Intent detection and targeted WhatMobile phone resolution for the chatbot."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from whatmobile.models import WhatMobilePhone
from whatmobile.phone_filters import comparison_phone_queryset
from whatmobile.phone_matcher import _match_score, _name_tokens

IntentKind = Literal[
    "greeting",
    "compare_models",
    "compare_brands",
    "single_phone",
    "worth_buying",
    "recommend",
    "feature_focus",
    "pros_cons",
    "general",
]

FeatureFocus = Literal["camera", "battery", "gaming", "display", "value", "software", "performance", ""]

_COMPARE_SPLIT = re.compile(r"\s+(?:or|vs\.?|versus)\s+", re.IGNORECASE)

_MODEL_PATTERNS = (
    r"(iphone\s+\d+\s*(?:pro\s*max|pro|max|plus|mini|air|e)?)",
    r"(galaxy\s+(?:s\d+\s*ultra|s\d+\+|s\d+|a\d+|z\s*fold\s*\d+|z\s*flip\s*\d+))",
    r"\b(s\d+\s*ultra|s\d+\+|s\d+|a\d+)\b",
)

_VARIANT_MARKERS = ("pro max", "pro", "max", "plus", "mini", "ultra", "fe", "e")

_FEATURE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "camera": ("camera", "photography", "photo", "selfie"),
    "battery": ("battery", "battery life", "charging", "endurance"),
    "gaming": ("gaming", "game", "pubg", "fps", "gamer"),
    "display": ("display", "screen", "refresh rate"),
    "value": ("value for money", "value", "worth the money", "budget"),
    "software": ("software", "ios", "one ui", "updates", "ecosystem"),
    "performance": ("performance", "speed", "processor", "chip", "fast"),
}

_WORTH_BUYING = (
    "worth buying",
    "still worth",
    "should i buy",
    "good buy",
    "worth it",
    "buy in 202",
)

_RECOMMEND = (
    "recommend",
    "suggest",
    "which phone should",
    "which should i buy",
    "best phone",
    "top phone",
    "what phone",
)

_COMPARE = (
    "better",
    "compare",
    "comparison",
    " vs ",
    "versus",
    "which is better",
    "which phone is better",
    "difference between",
    "differences between",
)

_PROS_CONS = ("pros and cons", "advantages and disadvantages", "advantages", "disadvantages", "pros", "cons")

_FOLLOW_UP = (
    "what about",
    "how about",
    "and the",
    "tell me more",
    "more about",
    "which one",
    "which has",
    "between them",
    "between these",
    "same question",
    "that one",
    "those two",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


@dataclass
class ChatIntent:
    kind: IntentKind
    message: str
    model_phrases: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    budget: int | None = None
    feature: FeatureFocus = ""
    use_case: str = ""
    context_message: str = ""


def _base_queryset():
    return comparison_phone_queryset()


def _extract_model_keywords(text: str) -> list[str]:
    t = _normalize(text)
    keywords: list[str] = []
    for pattern in _MODEL_PATTERNS:
        for match in re.finditer(pattern, t):
            kw = match.group(1).strip()
            if kw and kw not in keywords:
                keywords.append(kw)
    return keywords


def _extract_from_segment(segment: str) -> list[str]:
    keywords = _extract_model_keywords(segment)
    if keywords:
        return keywords
    t = _normalize(segment)
    if "galaxy" in t or "samsung" in t:
        m = re.search(r"\bs(\d+)\b", t)
        if m:
            return [f"s{m.group(1)}"]
    return []


def extract_model_phrases(text: str) -> list[str]:
    """Pull distinct model phrases, respecting comparison splits (or / vs / versus)."""
    text = (text or "").strip()
    if not text:
        return []

    phrases: list[str] = []
    if _COMPARE_SPLIT.search(text):
        for segment in _COMPARE_SPLIT.split(text):
            phrases.extend(_extract_from_segment(segment))
    else:
        phrases.extend(_extract_model_keywords(text))

    seen: set[str] = set()
    unique: list[str] = []
    for phrase in phrases:
        key = _normalize(phrase)
        if key not in seen:
            seen.add(key)
            unique.append(phrase)

    # Drop bare "s22" when "galaxy s22" is already present.
    normalized = {_normalize(p) for p in unique}
    filtered: list[str] = []
    for phrase in unique:
        p = _normalize(phrase)
        if re.fullmatch(r"s\d+\+?", p):
            if any(p in other and other != p for other in normalized):
                continue
        filtered.append(phrase)
    return filtered


def _parse_budget(text: str) -> int | None:
    t = _normalize(text)
    m = re.search(r"(?:under|below|less than|upto|up to|max|within)\s*(?:rs\.?|pkr)?\s*([\d,]+)", t)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r"([\d]+)\s*(?:lac|lakh)", t)
    if m:
        return int(m.group(1)) * 100000
    m = re.search(r"(?:rs\.?|pkr)\s*([\d,]+)", t)
    if m and any(w in t for w in ("budget", "recommend", "best", "under", "below", "within")):
        return int(m.group(1).replace(",", ""))
    return None


def _detect_feature(text: str) -> FeatureFocus:
    t = _normalize(text)
    for feature, words in _FEATURE_KEYWORDS.items():
        if any(w in t for w in words):
            return feature  # type: ignore[return-value]
    return ""


def _detect_use_case(text: str) -> str:
    t = _normalize(text)
    cases = {
        "students": ("student", "students", "college", "university"),
        "everyday": ("everyday", "daily use", "day to day", "normal use"),
        "photography": ("photography", "photographer", "instagram"),
    }
    for label, words in cases.items():
        if any(w in t for w in words):
            return label
    return ""


def _mentions_iphone(text: str) -> bool:
    t = _normalize(text)
    return "iphone" in t or "apple" in t


def _mentions_samsung(text: str) -> bool:
    t = _normalize(text)
    return any(k in t for k in ("samsung", "galaxy", "fold", "flip")) or bool(
        re.search(r"\bs\d+\b", t)
    )


def _is_brand_only_comparison(text: str, model_phrases: list[str]) -> bool:
    if not (_mentions_iphone(text) and _mentions_samsung(text)):
        return False
    if model_phrases:
        return False
    t = _normalize(text)
    return any(w in t for w in _COMPARE) or "better" in t


def _is_comparison_query(text: str, model_phrases: list[str]) -> bool:
    t = _normalize(text)
    if len(model_phrases) >= 2:
        return True
    if _COMPARE_SPLIT.search(text) and model_phrases:
        return True
    return any(w in t for w in _COMPARE)


def _is_follow_up(text: str) -> bool:
    t = _normalize(text)
    if len(t.split()) > 12:
        return False
    return any(p in t for p in _FOLLOW_UP) or t.endswith("?")


def _contextual_message(message: str, history: list[dict]) -> str:
    """Enrich short follow-ups with the previous user turn."""
    if not history or not _is_follow_up(message):
        return message

    last_user = ""
    for turn in reversed(history):
        if turn.get("role") == "user":
            last_user = (turn.get("content") or "").strip()
            break

    if not last_user:
        return message

    return f"{last_user}\n\nFollow-up: {message}"


def detect_intent(message: str, history: list[dict] | None = None) -> ChatIntent:
    history = history or []
    raw = (message or "").strip()
    enriched = _contextual_message(raw, history)

    model_phrases = extract_model_phrases(enriched)
    budget = _parse_budget(enriched)
    feature = _detect_feature(enriched)
    use_case = _detect_use_case(enriched)
    t = _normalize(enriched)

    brands: list[str] = []
    if _mentions_iphone(enriched):
        brands.append("apple")
    if _mentions_samsung(enriched):
        brands.append("samsung")

    if _is_brand_only_comparison(enriched, model_phrases):
        return ChatIntent(
            kind="compare_brands",
            message=raw,
            brands=brands,
            feature=feature,
            use_case=use_case,
            context_message=enriched,
        )

    if _is_comparison_query(enriched, model_phrases):
        return ChatIntent(
            kind="compare_models",
            message=raw,
            model_phrases=model_phrases,
            brands=brands,
            feature=feature,
            use_case=use_case,
            context_message=enriched,
        )

    if any(p in t for p in _WORTH_BUYING):
        return ChatIntent(
            kind="worth_buying",
            message=raw,
            model_phrases=model_phrases,
            brands=brands,
            feature=feature,
            use_case=use_case,
            context_message=enriched,
        )

    if any(p in t for p in _PROS_CONS) and model_phrases:
        return ChatIntent(
            kind="pros_cons",
            message=raw,
            model_phrases=model_phrases,
            brands=brands,
            context_message=enriched,
        )

    if budget is not None or any(p in t for p in _RECOMMEND):
        return ChatIntent(
            kind="recommend",
            message=raw,
            model_phrases=model_phrases,
            brands=brands,
            budget=budget,
            feature=feature,
            use_case=use_case,
            context_message=enriched,
        )

    if feature and not model_phrases:
        return ChatIntent(
            kind="feature_focus",
            message=raw,
            brands=brands,
            feature=feature,
            use_case=use_case,
            context_message=enriched,
        )

    if model_phrases:
        return ChatIntent(
            kind="single_phone",
            message=raw,
            model_phrases=model_phrases[:1],
            brands=brands,
            feature=feature,
            context_message=enriched,
        )

    if brands and len(brands) == 1:
        return ChatIntent(
            kind="general",
            message=raw,
            brands=brands,
            feature=feature,
            context_message=enriched,
        )

    return ChatIntent(kind="general", message=raw, context_message=enriched)


def _variant_penalty(phrase: str, model_name: str) -> int:
    """Prefer the base model when the user did not ask for a variant."""
    p = _normalize(phrase)
    m = _normalize(model_name)
    penalty = 0
    for marker in _VARIANT_MARKERS:
        if marker not in p and marker in m:
            penalty += 600
    if re.search(r"\biphone\s+\d+\b", p) and re.search(r"\biphone\s+\d+\b", m):
        p_num = re.search(r"\biphone\s+(\d+)", p)
        m_num = re.search(r"\biphone\s+(\d+)", m)
        if p_num and m_num and p_num.group(1) == m_num.group(1):
            if p.strip() == re.search(r"iphone\s+\d+", p).group(0).strip():
                if any(v in m for v in ("pro", "max", "mini", "plus")):
                    penalty += 800
    return penalty


def _candidate_queryset_for_phrase(phrase: str):
    """Narrow candidates with DB filters before scoring."""
    t = _normalize(phrase)
    qs = _base_queryset()
    if "iphone" in t:
        qs = qs.filter(model_name__icontains="iphone")
    elif "galaxy" in t or re.search(r"\bs\d+", t):
        qs = qs.filter(model_name__icontains="galaxy")
    nums = re.findall(r"\d+", t)
    for num in nums[:2]:
        qs = qs.filter(model_name__icontains=num)
    return qs.only("id", "model_name", "brand", "official_price", "official_price_value", "updated_at")[:80]


def best_phone_for_phrase(phrase: str) -> WhatMobilePhone | None:
    """Return the single best-matching phone for a model phrase."""
    needle = _name_tokens(phrase)
    if not needle:
        return None

    best_phone = None
    best_score = 0
    for phone in _candidate_queryset_for_phrase(phrase):
        haystack = _name_tokens(phone.model_name)
        score = _match_score(needle, haystack)
        score -= _variant_penalty(phrase, phone.model_name)
        if score > best_score:
            best_score = score
            best_phone = phone

    if best_score >= 500 and best_phone:
        return WhatMobilePhone.objects.using("whatmobile").filter(pk=best_phone.id).first()
    return None


def _dedupe_phones(phones: list[WhatMobilePhone]) -> list[WhatMobilePhone]:
    seen: set[int] = set()
    unique: list[WhatMobilePhone] = []
    for phone in phones:
        if phone.id in seen:
            continue
        seen.add(phone.id)
        unique.append(phone)
    return unique


def _phone_price_value(phone: WhatMobilePhone) -> int | None:
    from whatmobile.phone_matcher import resolve_phone_price

    price_info = resolve_phone_price(phone)
    price = price_info.get("price")
    if price and price > 0:
        return int(price)
    if phone.official_price_value and phone.official_price_value > 0:
        return int(phone.official_price_value)
    return None


def _representative_phones(brand: str, limit: int = 2) -> list[WhatMobilePhone]:
    """Pick recent flagship-style models for brand-level comparisons."""
    qs = _base_queryset().filter(brand=brand)
    if brand == "apple":
        qs = qs.filter(model_name__icontains="iphone").exclude(model_name__icontains="se")
    else:
        qs = qs.filter(model_name__iregex=r"galaxy\s+s\d+")

    scored: list[tuple[int, WhatMobilePhone]] = []
    for phone in qs:
        m = _normalize(phone.model_name)
        if "se" in m.split():
            continue
        score = 0
        num = re.search(r"iphone\s+(\d+)", m) or re.search(r"s(\d+)", m)
        if num:
            score += int(num.group(1)) * 10
        if "ultra" in m:
            score += 4
        if re.search(r"\bpro\b", m):
            score += 2
        if "plus" in m:
            score += 1
        scored.append((score, phone))

    scored.sort(key=lambda x: x[0], reverse=True)
    return _dedupe_phones([p for _, p in scored])[:limit]


def _phones_within_budget(budget: int, brands: list[str], limit: int = 5) -> list[WhatMobilePhone]:
    qs = _base_queryset().filter(
        official_price_value__lte=budget,
        official_price_value__gt=0,
    )
    if brands == ["apple"]:
        qs = qs.filter(brand="apple")
    elif brands == ["samsung"]:
        qs = qs.filter(brand="samsung")

    phones = list(qs.order_by("-official_price_value")[: limit * 2])
    return _dedupe_phones(phones)[:limit]


def _feature_candidates(feature: str, brands: list[str], limit: int = 4) -> list[WhatMobilePhone]:
    """Return a small set of recent phones to reason about a feature-focused question."""
    qs = _base_queryset()
    if brands == ["apple"]:
        qs = qs.filter(brand="apple")
    elif brands == ["samsung"]:
        qs = qs.filter(brand="samsung")
    return _dedupe_phones(list(qs.order_by("-updated_at")[:limit * 3]))[:limit]


def resolve_phones(intent: ChatIntent) -> list[WhatMobilePhone]:
    """Map detected intent to the smallest relevant set of WhatMobile records."""
    if intent.kind == "compare_models":
        phones: list[WhatMobilePhone] = []
        for phrase in intent.model_phrases[:4]:
            phone = best_phone_for_phrase(phrase)
            if phone:
                phones.append(phone)
        return _dedupe_phones(phones)

    if intent.kind == "compare_brands":
        phones: list[WhatMobilePhone] = []
        if "apple" in intent.brands:
            phones.extend(_representative_phones("apple", limit=2))
        if "samsung" in intent.brands:
            phones.extend(_representative_phones("samsung", limit=2))
        return _dedupe_phones(phones)

    if intent.kind in {"single_phone", "worth_buying", "pros_cons"}:
        if intent.model_phrases:
            phone = best_phone_for_phrase(intent.model_phrases[0])
            return [phone] if phone else []
        return []

    if intent.kind == "recommend":
        if intent.budget:
            return _phones_within_budget(intent.budget, intent.brands, limit=5)
        if intent.brands == ["apple"]:
            return _representative_phones("apple", limit=4)
        if intent.brands == ["samsung"]:
            return _representative_phones("samsung", limit=4)
        return _dedupe_phones(
            list(_base_queryset().order_by("-updated_at")[:6])
        )[:5]

    if intent.kind == "feature_focus":
        return _feature_candidates(intent.feature, intent.brands, limit=4)

    if intent.kind == "general" and intent.brands:
        return _representative_phones(intent.brands[0], limit=3)

    if intent.model_phrases:
        phone = best_phone_for_phrase(intent.model_phrases[0])
        return [phone] if phone else []

    return []


INTENT_INSTRUCTIONS: dict[IntentKind, str] = {
    "compare_models": "Compare ONLY these two phones. Summary, table, pros/cons, recommendation.",
    "compare_brands": "Compare iPhone vs Samsung brands using sample phones. No model catalog.",
    "single_phone": "Answer about this one phone only.",
    "worth_buying": "Is it worth buying today? Clear yes/no/maybe with reasons.",
    "recommend": "Rank best phones from data for user's budget/needs.",
    "feature_focus": "Focus on the user's priority feature and recommend the best option.",
    "pros_cons": "List pros, cons, and a short verdict.",
    "general": "Answer naturally using only the provided data.",
}
