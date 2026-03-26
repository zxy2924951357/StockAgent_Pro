# agent/general.py
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

load_dotenv()
CURRENT_MODEL = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
llm = ChatOpenAI(model=CURRENT_MODEL, temperature=0)

# 🚀 彻底封印闲聊助理的“客服感”和 Emoji
GENERAL_PROMPT = """你是一个耐心、客观的金融百科助理。
核心功能：承担系统的兜底作用。处理与实时行情无关的闲聊、名词解释、公司主营业务介绍等。

【核心格式铁律：违反将被抹杀】
1. 语气必须像经验丰富的老前辈聊天，连贯自然，用大白话解释复杂概念。
2. 绝对禁止使用任何 Emoji (如 😊, 🔹, 💡, 🤖 等)。
3. 绝对禁止使用复杂的 Markdown 排版（不要用粗体、不要列生硬的黑点清单）。
4. 段落之间保持紧凑，绝对不要输出多余的空行。
5. 自然结束，绝对不要加上任何类似“随时问我哦！”这种套路化的客服结束语。"""

general_agent = create_react_agent(
    llm,
    tools=[]
)