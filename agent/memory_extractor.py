import os
import logging
import datetime
from typing import Literal

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from core.db_manager import mongo_manager

logger = logging.getLogger("memory_extractor")


class UserProfileExtraction(BaseModel):
    risk_preference: Literal["激进", "稳健", "保守", "未知"] = Field(
        default="未知",
        description="用户风险偏好。只能四选一：激进/稳健/保守/未知。",
    )
    trading_style: str = Field(
        default="",
        description="用户交易风格关键词，如右侧交易、趋势跟随、价值投资、短线波段等。",
    )
    notes: str = Field(
        default="",
        description="可用于研报个性化建议的简短备注，最多一句话。",
    )
    confidence: float = Field(
        default=0.0,
        description="本次画像提取置信度，范围 0 到 1。",
    )


async def extract_user_profile(user_query: str, user_id: str) -> None:
    """
    从用户自然语言中静默提取画像并持久化到 user_profile 集合。
    失败时只记录日志，不抛出异常，不影响主流程。
    """
    try:
        if not user_query or not user_query.strip():
            return
        if not user_id or not str(user_id).strip():
            return

        model_name = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
        llm = ChatOpenAI(model=model_name, temperature=0).with_structured_output(UserProfileExtraction)

        prompt = f"""
你是资深投顾系统的用户画像抽取器。请根据用户一句话输入，提取稳定画像信息。
规则：
1) 只从用户这句话中提取，不得臆测。
2) 若证据不足，risk_preference 必须返回 "未知"。
3) trading_style 使用短语，不超过 12 个字；无信息则留空。
4) notes 为一句简短备注；无信息则留空。
5) confidence 在 0 到 1 之间。

用户输入：
{user_query}
"""
        profile = await llm.ainvoke(prompt)

        now = datetime.datetime.now()
        doc = {
            "user_id": user_id,
            "risk_preference": profile.risk_preference,
            "trading_style": (profile.trading_style or "").strip(),
            "notes": (profile.notes or "").strip(),
            "confidence": float(profile.confidence or 0.0),
            "updated_at": now,
            "last_query": user_query[:500],
        }

        await mongo_manager.db["user_profile"].update_one(
            {"user_id": user_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        logger.info(f"🧠 用户画像已更新: user_id={user_id}, risk={doc['risk_preference']}, style={doc['trading_style']}")
    except Exception as e:
        logger.warning(f"⚠️ 用户画像提取失败(已忽略): {e}")

