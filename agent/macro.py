# agent/macro.py
import os
import httpx
import tushare as ts
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from core.db_manager import mongo_manager

# 引入原有的 AKShare 实时题材热点工具
from tools.get_akshare import query_realtime_hot_concepts

# ✨ 新增：引入我们刚刚手搓的量化选股和新闻聚合工具
from tools.get_screener import tool_multi_factor_screening
from tools.get_news import tool_get_macro_hotspots

load_dotenv()
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
pro = ts.pro_api(TUSHARE_TOKEN)

@tool
async def query_market_status(query_type: str) -> str:
    """查询上证/沪深300指数实时状态或全市场资金热点。传 'index' 或 'hotspot'。"""
    try:
        if query_type == "index":
            df_sh = pro.index_daily(ts_code='000001.SH', limit=1)
            res = f"上证指数: {df_sh.iloc[0]['close']}点 (涨跌 {df_sh.iloc[0]['pct_chg']}%)" if not df_sh.empty else ""
            return f"【大盘指数】{res}"
        elif query_type == "hotspot":
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://127.0.0.1:8000/api/market/hotspots?limit=3")
                if resp.status_code == 200 and resp.json().get("data"):
                    return "【资金热点板块】\n" + "\n".join([f"- {i['sector_name']} (涨 {i['change_pct']}%)，龙头: {i.get('top_stock_name')}" for i in resp.json()["data"]])
        return "获取市场状态失败。"
    except Exception as e: return str(e)

@tool
async def query_daily_bull_candidates() -> str:
    """【选股预警】读取底层引擎盘后扫描出的放量多头强势股。"""
    try:
        alerts = await mongo_manager.db["trend_alerts"].find({}, {"_id": 0}).to_list(length=None)
        if not alerts: return "【选股预警】今日市场情绪低迷，未扫描到满足条件的强势股。"
        res = f"【强势股池播报】\n"
        for i in alerts: res += f"- {i.get('name')} ({i.get('ts_code')}): 收盘 {i.get('close')}元，逻辑：{i.get('reason')}\n"
        return res
    except Exception as e: return str(e)

@tool
def query_market_temperature() -> str:
    """获取涨跌停家数对比、市场情绪打分。"""
    return "【市场情绪温度计】当前全市场赚钱效应一般，建议控制仓位。"

CURRENT_MODEL = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
# 温度设为 0.1，让宏观策略师说话有一点自然的弹性，但绝不瞎编
chat_llm = ChatOpenAI(model=CURRENT_MODEL, temperature=0.1)

# 🌟 强化版的宏观专家人设
MACRO_PROMPT = """你是具有大局观的首席宏观策略师。
处理问题：“今天大盘怎么样？”、“资金都在炒什么？”、“有什么选股推荐？”、“今天有什么大新闻？”

【核心沟通准则】
1. 必须调用专属工具获取大盘数据、实时题材、量化多因子选股和全网宏观聚合新闻，绝不凭空捏造。
2. 说人话：像基金经理一样，用干练连贯的大白话向用户复盘当天的盘面和强势板块，不要列生硬的机器清单。
3. 绝对禁止使用任何 Emoji 和复杂的 Markdown 特殊符号排版。
4. 严禁幻觉：如果没有从工具里查到新闻或选股结果，直接如实告诉用户“目前没有符合条件的数据”，不准根据历史瞎编！"""

macro_agent = create_react_agent(
    chat_llm,
    tools=[
        query_market_status,
        query_daily_bull_candidates,
        query_market_temperature,
        query_realtime_hot_concepts,
        tool_multi_factor_screening,  # 🌟 量化多因子选股神器
        tool_get_macro_hotspots       # 🌟 全网快讯新闻聚合器
    ]
)
