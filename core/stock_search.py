import asyncio
import re
from typing import Any, Dict, List

from pypinyin import Style, lazy_pinyin
from pymongo import UpdateOne

_SEARCH_INDEX_READY = False
_SEARCH_INDEX_LOCK = asyncio.Lock()


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", (keyword or "").strip()).lower()


def build_name_search_fields(name: str) -> Dict[str, str]:
    normalized_name = re.sub(r"\s+", "", (name or "").strip())
    if not normalized_name:
        return {"name_pinyin": "", "name_initials": ""}

    full_pinyin = "".join(lazy_pinyin(normalized_name, errors="ignore")).lower()
    initials = "".join(
        lazy_pinyin(normalized_name, style=Style.FIRST_LETTER, errors="ignore")
    ).lower()
    return {"name_pinyin": full_pinyin, "name_initials": initials}


def build_stock_search_query(keyword: str) -> Dict[str, Any]:
    normalized = normalize_keyword(keyword)
    if not normalized:
        return {}

    escaped = re.escape(normalized)
    code_regex = {"$regex": escaped, "$options": "i"}
    prefix_regex = {"$regex": f"^{escaped}", "$options": "i"}

    return {
        "$or": [
            {"ts_code": code_regex},
            {"symbol": prefix_regex},
            {"name": {"$regex": re.escape((keyword or "").strip()), "$options": "i"}},
            {"name_pinyin": prefix_regex},
            {"name_initials": prefix_regex},
            {"name_pinyin": code_regex},
            {"name_initials": code_regex},
        ]
    }


def score_stock_match(stock: Dict[str, Any], keyword: str) -> int:
    normalized = normalize_keyword(keyword)
    if not normalized:
        return 0

    ts_code = (stock.get("ts_code") or "").lower()
    symbol = (stock.get("symbol") or "").lower()
    name = (stock.get("name") or "").lower()
    name_pinyin = (stock.get("name_pinyin") or "").lower()
    name_initials = (stock.get("name_initials") or "").lower()

    score = 0
    if ts_code == normalized or symbol == normalized:
        score += 100
    elif ts_code.startswith(normalized) or symbol.startswith(normalized):
        score += 80
    elif normalized in ts_code or normalized in symbol:
        score += 60

    if name == normalized:
        score += 90
    elif name.startswith(normalized):
        score += 70
    elif normalized in name:
        score += 50

    if name_pinyin == normalized or name_initials == normalized:
        score += 85
    elif name_pinyin.startswith(normalized) or name_initials.startswith(normalized):
        score += 75
    elif normalized in name_pinyin or normalized in name_initials:
        score += 55

    score -= len(name)
    return score


async def ensure_stock_search_fields(collection) -> None:
    global _SEARCH_INDEX_READY

    if _SEARCH_INDEX_READY:
        return

    async with _SEARCH_INDEX_LOCK:
        if _SEARCH_INDEX_READY:
            return

        cursor = collection.find(
            {
                "$or": [
                    {"name_pinyin": {"$exists": False}},
                    {"name_initials": {"$exists": False}},
                    {"name_pinyin": ""},
                    {"name_initials": ""},
                ]
            },
            {"_id": 1, "name": 1},
        )

        operations: List[UpdateOne] = []
        async for stock in cursor:
            fields = build_name_search_fields(stock.get("name", ""))
            operations.append(
                UpdateOne(
                    {"_id": stock["_id"]},
                    {"$set": fields},
                )
            )

            if len(operations) >= 500:
                await collection.bulk_write(operations, ordered=False)
                operations = []

        if operations:
            await collection.bulk_write(operations, ordered=False)

        _SEARCH_INDEX_READY = True
