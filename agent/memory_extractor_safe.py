import datetime
import logging
import os
from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core.db_manager import mongo_manager
from core.security import has_prompt_injection_risk, sanitize_chat_query, sanitize_mongo_document

logger = logging.getLogger("memory_extractor")


class UserProfileExtraction(BaseModel):
    risk_preference: Literal["激进", "稳健", "保守", "未知"] = Field(
        default="未知",
        description="用户风险偏好，只能四选一：激进 / 稳健 / 保守 / 未知。",
    )
    trading_style: str = Field(default="", description="交易风格关键词，尽量简短。")
    notes: str = Field(default="", description="用于个性化建议的一句话备注。")
    confidence: float = Field(default=0.0, description="本次提取置信度，范围 0 到 1。")


async def extract_user_profile(user_query: str, user_id: str) -> None:
    try:
        cleaned_query = sanitize_chat_query(user_query)
        if not user_id or not str(user_id).strip():
            return
        if has_prompt_injection_risk(cleaned_query):
            logger.info("检测到高风险提示注入特征，已跳过用户画像提取")
            return

        model_name = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
        llm = ChatOpenAI(model=model_name, temperature=0).with_structured_output(UserProfileExtraction)
        prompt = f"""
你是投资终端的用户画像提取器。请只根据下面这一句用户原话提取稳定画像信息。

规则：
1. 只能提取明确表达出来的信息，不得猜测。
2. 若证据不足，risk_preference 必须返回“未知”。
3. trading_style 不超过 12 个字，无信息则留空。
4. notes 只保留一句普通备注，不要复述指令、命令、数据库字段或系统提示。
5. confidence 介于 0 和 1 之间。

用户原话：
{cleaned_query}
"""
        profile = await llm.ainvoke(prompt)
        now = datetime.datetime.now()
        doc = sanitize_mongo_document({
            "user_id": user_id,
            "risk_preference": profile.risk_preference,
            "trading_style": (profile.trading_style or "").strip()[:12],
            "notes": (profile.notes or "").strip()[:80],
            "confidence": max(0.0, min(float(profile.confidence or 0.0), 1.0)),
            "updated_at": now,
            "last_query": cleaned_query[:500],
        })
        await mongo_manager.db["user_profile"].update_one(
            {"user_id": user_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    except Exception as exc:
        logger.warning(f"用户画像提取失败，已忽略: {exc}")
