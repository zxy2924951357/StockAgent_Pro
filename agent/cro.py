# agent/cro.py
import os
import logging
import httpx
import pandas as pd
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

# 🌟 关键引入：让 CRO 也能直接调用底层的真实资金流向工具
from tools.get_akshare import query_stock_fund_flow

load_dotenv()
logger = logging.getLogger("agent_cro")

# 温度设为 0.1，保留一丝对话的灵活性，但绝对冷静
CURRENT_MODEL = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
cro_llm = ChatOpenAI(model=CURRENT_MODEL, temperature=0.1)


def get_em_secid(ts_code: str) -> str:
    code = ts_code[:6]
    return f"1.{code}" if code.startswith(('6', '9', '5')) else f"0.{code}"


async def get_real_technical_data(ts_code: str):
    secid = get_em_secid(ts_code)
    url = f"http://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500000&lmt=60"
    try:
        async with httpx.AsyncClient(verify=False) as client:
            res = await client.get(url, timeout=5.0)
            klines = res.json().get("data", {}).get("klines", [])
            if not klines: return None
            parsed = [{"close": float(k.split(",")[2]), "high": float(k.split(",")[3]), "low": float(k.split(",")[4])}
                      for k in klines]
            df = pd.DataFrame(parsed)
            return {
                "ma20": round(df['close'].rolling(20).mean().iloc[-1], 2),
                "high_60d": df['high'].max(),
                "low_60d": df['low'].min()
            }
    except:
        return None


# ==================== 🌟 核心防戏精红线 ====================
ANTI_FAKE_TRADE_RULE = """
【🔴 核心系统红线】：本系统为纯粹的量化分析终端，绝对不具备自动交易、下单和一键调仓功能！
你只能给出策略建议，绝对禁止在回答末尾说出类似“请确认是否执行”、“我将在X分钟内为您完成交易部署”、“已为您发送交易指令”、“请确认”等戏精话术！
绝对不能向用户请示交易确认，说完盘面分析和建议必须立即结束对话！
"""


# =========================================================

# 🌟 核心升级 1：支持自然语言问答的单票风控
async def stream_cro_diagnosis(stock_name: str, ts_code: str, volume: int, cost_price: float, current_price: float,
                               profit_status: str, user_query: str):
    tech_data = await get_real_technical_data(ts_code)
    tech_str = ""
    if tech_data:
        tech_str = f"【系统盘面数据】20日线: {tech_data['ma20']}元 | 60日内高点: {tech_data['high_60d']}元 | 60日内低点: {tech_data['low_60d']}元\n"

    try:
        fund_flow_str = query_stock_fund_flow.invoke(ts_code)
    except:
        fund_flow_str = "【资金面数据】暂无最新资金流向明细。"

    prompt = f"""
    你是顶级量化私募的【首席风控官(CRO)】。
    客户指令/提问："{user_query}"

    【后台调取的客户真实数据】
    - 标的：{stock_name} ({ts_code})
    - 持有数量：{volume} 股
    - 买入成本价：{cost_price} 元
    - 当前市价：{current_price} 元
    - 当前盈亏：【{profit_status}】

    {tech_str}
    {fund_flow_str}

    {ANTI_FAKE_TRADE_RULE}

    请根据以上客观数据（技术面+主力资金面），冷酷、专业、一针见血地直接回答客户。
    要求：
    1. 直接告诉他成本是多少、赚了还是亏了（净值与安全垫评估）。
    2. 结合技术面和主力资金流向，给出你确切的操作建议（如：现价割肉 / 死扛等待 / 逢高减仓 / 突破加仓）。
    3. 坚决不要废话，不要推测没有的数据。
    """

    async for chunk in cro_llm.astream([HumanMessage(content=prompt)]):
        if chunk.content:
            yield chunk.content


# 🌟 核心升级 2：支持全局账户盘点的风控大盘
async def stream_global_portfolio_chat(portfolio_summary: str, user_query: str):
    prompt = f"""
    你是顶级量化私募的【首席风控官(CRO)】。
    你的客户问了关于他整个账户持仓的问题："{user_query}"

    【后台调取的客户全局持仓账单与实时盈亏】
    {portfolio_summary}

    {ANTI_FAKE_TRADE_RULE}

    【🔴 全局视角与微观操作的界限纪律】：
    你当前处于“全局宏观盘点”模式。你眼前只有各只股票的盈亏账单，【没有】单只股票的实时技术面和主力资金流向数据！
    因此：
    1. 你只能从“仓位权重”、“账户集中度风险”、“整体盈亏拖累”等【宏观结构】角度进行评价。
    2. 指出“出血点”（如哪些股票亏损绝对值极大）和“利润垫”。
    3. 绝对禁止对单只股票（如万丰奥威、科大讯飞等）下达具体的“割肉、止损、加仓”等微观交易结论！因为你现在处于缺少资金面数据的“盲人摸象”状态。
    4. 如果提到具体股票的后续操作，必须统一回复并提醒客户：“关于单只标的的具体买卖点，请点击该股票的 [风控诊断] 按钮，调取其主力资金流向后再做微观决断。”
    """
    async for chunk in cro_llm.astream([HumanMessage(content=prompt)]):
        if chunk.content:
            yield chunk.content