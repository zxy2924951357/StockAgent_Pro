import re
from typing import Any

from fastapi import HTTPException


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]{3,24}$")
TS_CODE_PATTERN = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$", re.IGNORECASE)
HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")

PROMPT_INJECTION_MARKERS = (
    "忽略之前",
    "system prompt",
    "developer message",
    "数据库",
    "db.",
    "$where",
    "$set",
    "$regex",
    "drop table",
    "delete from",
    "update users",
    "mongo",
)


def sanitize_text(value: Any, *, field_name: str = "字段", max_length: int = 200, allow_newlines: bool = False) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field_name}格式无效")

    cleaned = value.replace("\x00", "").strip()
    if not allow_newlines:
        cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) > max_length:
        raise HTTPException(status_code=400, detail=f"{field_name}长度不能超过 {max_length} 个字符")
    return cleaned


def validate_username(username: Any) -> str:
    cleaned = sanitize_text(username, field_name="用户名", max_length=24)
    if not USERNAME_PATTERN.fullmatch(cleaned):
        raise HTTPException(status_code=400, detail="用户名需为 3-24 位，可包含中文、字母、数字、下划线或短横线")
    return cleaned


def validate_password(password: Any, *, field_name: str = "密码") -> str:
    if not isinstance(password, str):
        raise HTTPException(status_code=400, detail=f"{field_name}格式无效")
    cleaned = password.strip()
    if len(cleaned) < 6 or len(cleaned) > 64:
        raise HTTPException(status_code=400, detail=f"{field_name}长度需为 6-64 位")
    return cleaned


def normalize_ts_code(ts_code: Any, *, required: bool = True) -> str:
    cleaned = sanitize_text(ts_code, field_name="股票代码", max_length=16).upper()
    if not cleaned and not required:
        return ""
    if not TS_CODE_PATTERN.fullmatch(cleaned):
        raise HTTPException(status_code=400, detail="股票代码格式无效，应为 000001.SZ / 600000.SH")
    return cleaned


def sanitize_stock_name(name: Any) -> str:
    cleaned = sanitize_text(name, field_name="股票名称", max_length=40)
    if not cleaned:
        raise HTTPException(status_code=400, detail="股票名称不能为空")
    return cleaned


def sanitize_avatar_url(avatar_url: Any) -> str:
    cleaned = sanitize_text(avatar_url, field_name="头像地址", max_length=2_000_000)
    if cleaned.startswith("data:image/"):
        return cleaned
    if cleaned.startswith("https://") or cleaned.startswith("http://"):
        return cleaned
    raise HTTPException(status_code=400, detail="头像仅支持 http(s) 地址或 data:image 数据")


def sanitize_theme(theme: Any) -> str:
    cleaned = sanitize_text(theme, field_name="主题", max_length=8)
    if cleaned not in {"day", "night"}:
        raise HTTPException(status_code=400, detail="主题仅支持白天或黑夜")
    return cleaned


def sanitize_risk_preference(value: Any) -> str:
    cleaned = sanitize_text(value, field_name="风险偏好", max_length=12)
    if cleaned not in {"激进", "稳健", "保守", "未知"}:
        raise HTTPException(status_code=400, detail="风险偏好仅支持 激进 / 稳健 / 保守 / 未知")
    return cleaned


def sanitize_chat_query(query: Any) -> str:
    cleaned = sanitize_text(query, field_name="聊天内容", max_length=2000, allow_newlines=True)
    if not cleaned:
        raise HTTPException(status_code=400, detail="聊天内容不能为空")
    return cleaned


def has_prompt_injection_risk(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker.lower() in lowered for marker in PROMPT_INJECTION_MARKERS)


def sanitize_mongo_document(value: Any) -> Any:
    if isinstance(value, dict):
        safe_doc = {}
        for key, item in value.items():
            if isinstance(key, str) and ("." in key or key.startswith("$")):
                continue
            safe_doc[key] = sanitize_mongo_document(item)
        return safe_doc
    if isinstance(value, list):
        return [sanitize_mongo_document(item) for item in value]
    if isinstance(value, str):
        return value.replace("\x00", "").strip()
    return value
