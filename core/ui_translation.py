import json
import os
import re
from typing import Iterable, List

from langchain_openai import ChatOpenAI


CURRENT_MODEL = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
_HAS_TRANSLATOR = bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))
_TRANSLATOR = ChatOpenAI(model=CURRENT_MODEL, temperature=0) if _HAS_TRANSLATOR else None
_LOCAL_CACHE = {}
_CJK_RE = re.compile(r"[\u3400-\u9fff]")

STATIC_EN_MAP = {
    "上证指数": "SSE Composite",
    "深证成指": "SZSE Component",
    "创业板指": "ChiNext Index",
    "人工智能(缓存)": "Artificial Intelligence (Cached)",
    "光通信(缓存)": "Optical Communication (Cached)",
    "半导体(缓存)": "Semiconductors (Cached)",
    "稳健": "Conservative",
    "趋势跟踪 / 波段交易": "Trend Following / Swing Trading",
    "画像持续更新中。": "Your profile is still being updated.",
    "风险偏好": "Risk Preference",
    "短线敏捷": "Short-Term Agility",
    "中线耐心": "Medium-Term Patience",
    "仓位管理": "Position Management",
    "纪律执行": "Discipline",
}


def _normalize_text(value) -> str:
    return str(value or "").strip()


def contains_cjk(value: str) -> bool:
    return bool(_CJK_RE.search(_normalize_text(value)))


def _extract_json_array(content: str) -> List[str]:
    content = (content or "").strip()
    fenced_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", content)
    if fenced_match:
        content = fenced_match.group(1)
    else:
        array_match = re.search(r"(\[[\s\S]*\])", content)
        if array_match:
            content = array_match.group(1)
    parsed = json.loads(content)
    if isinstance(parsed, list):
        return [str(item or "").strip() for item in parsed]
    return []


async def _translate_missing_batch(texts: List[str], domain: str) -> List[str]:
    if not texts or not _TRANSLATOR:
        return texts

    prompt = f"""
You translate Chinese financial product UI text into concise natural English.
Return only a valid JSON array of translated strings in the same order as the input array.

Rules:
1. Translate stock names, sector names, user profile labels, and short financial notes.
2. Keep stock codes, numbers, punctuation, percentages, and ticker symbols unchanged.
3. Prefer standard market English when obvious.
4. Do not add explanations.
5. Domain: {domain}

Input:
{json.dumps(texts, ensure_ascii=False)}
"""
    try:
        result = await _TRANSLATOR.ainvoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        translated = _extract_json_array(content)
        if len(translated) == len(texts):
            return translated
    except Exception:
        pass
    return texts


async def translate_texts_to_english(texts: Iterable[str], domain: str = "ui") -> List[str]:
    source_list = [_normalize_text(text) for text in texts]
    if not source_list:
        return []

    resolved = {}
    missing = []
    for text in dict.fromkeys(source_list):
        if not text:
            resolved[text] = text
            continue
        if text in STATIC_EN_MAP:
            resolved[text] = STATIC_EN_MAP[text]
            continue
        if not contains_cjk(text):
            resolved[text] = text
            continue
        cache_key = f"en-US::{domain}::{text}"
        cached = _LOCAL_CACHE.get(cache_key)
        if cached:
            resolved[text] = cached
            continue
        missing.append(text)

    translated_missing = await _translate_missing_batch(missing, domain)
    for src, dst in zip(missing, translated_missing):
        final_text = _normalize_text(dst) or src
        cache_key = f"en-US::{domain}::{src}"
        _LOCAL_CACHE[cache_key] = final_text
        resolved[src] = final_text

    return [resolved.get(text, text) for text in source_list]
