# agent/fundamental.py
import os
import tushare as ts
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from core.db_manager import mongo_manager

load_dotenv()
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
pro = ts.pro_api(TUSHARE_TOKEN)

@tool
async def query_stock_basic_info(ts_code: str) -> str:
    """查询股票所属行业及主营业务。传入 ts_code。"""
    try:
        stock = await mongo_manager.db["stock_basic"].find_one({"ts_code": ts_code})
        base_info = f"{stock.get('name', '')} ({ts_code}) 属于 {stock.get('industry', '')} 行业。" if stock else ""
        df = pro.daily(ts_code=ts_code, limit=1)
        price_info = f"最新收盘价 {df.iloc[0]['close']} 元。" if not df.empty else ""
        return f"真实数据：{base_info} {price_info}" if base_info or price_info else f"未找到 {ts_code} 的信息。"
    except Exception as e: return f"基本面查询异常: {str(e)}"

@tool
def query_stock_valuation(ts_code: str) -> str:
    """查询股票核心估值(市盈率PE、市净率PB、总市值、换手率)。"""
    try:
        df = pro.daily_basic(ts_code=ts_code, limit=1)
        if df.empty: return f"未查到估值数据。"
        r = df.iloc[0]
        return f"【估值数据】总市值: {round(r.get('total_mv', 0) / 10000, 2)}亿元, 动态PE: {r.get('pe', '未知')}, PB: {r.get('pb', '未知')}, 换手率: {r.get('turnover_rate', '未知')}%"
    except Exception as e: return f"估值查询异常: {str(e)}"

@tool
async def query_financial_reports(ts_code: str) -> str:
    """查询近期财务健康度与排雷情况。"""
    try:
        fina_data = await mongo_manager.db["stock_fina"].find_one({"ts_code": ts_code}, sort=[("end_date", -1)])
        if not fina_data: return "【财务排雷】本地数据库暂未同步最新财报，无法进行排雷。"
        res = f"【财务排雷】财报期: {fina_data.get('end_date', '未知期')}\n"
        res += f"- 营业收入: {fina_data.get('revenue', '未知')} 元\n- 净利润: {fina_data.get('n_income', '未知')} 元\n"
        return res + "请根据上述利润情况评估盈利能力。"
    except Exception as e: return f"财务查询异常: {str(e)}"

CURRENT_MODEL = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
chat_llm = ChatOpenAI(model=CURRENT_MODEL, temperature=0)

# 🚀 终极“说人话”高情商人设
FUNDAMENTAL_PROMPT = """你是一位在股市摸爬滚打多年的资深财务老手。
你的任务是用最自然、接地气的大白话，像老朋友聊天一样给用户解答基本面和估值问题。

【核心沟通准则：违反将被抹杀】
1. 必须调用工具获取真实数据，基于事实说话，绝不凭空捏造。
2. 说人话：把冰冷的财务数字揉进自然的对话段落中。句子之间要有逻辑承接，像真人说话一样连贯，绝对不要像机器一样干巴巴地罗列“一、二、三”或列清单。
3. 语气要真诚、中肯。如果估值太高或数据缺失，直接用直白的话指出风险即可。严禁预测短线股价走势。
4. 纯净输出：严禁使用任何 Emoji (如 ✅, ⚠️ 等) 和生硬的特殊符号。严禁使用任何 Markdown 语法（不要加粗、不要用 # 标题格式）。
5. 自然结尾：绝不要给自己加戏，说完结论自然结束即可，严禁在文末加上任何形式的署名（如“—— 财务老手 敬上”）。"""

fund_agent = create_react_agent(
    chat_llm,
    tools=[query_stock_basic_info, query_stock_valuation, query_financial_reports]
)
