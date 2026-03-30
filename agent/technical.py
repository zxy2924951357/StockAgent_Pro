import os
import re
import tushare as ts
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from tools.get_akshare import query_stock_fund_flow
from tools.get_realtime import query_realtime_price

load_dotenv()
ts.set_token(os.getenv("TUSHARE_TOKEN", ""))
pro = ts.pro_api()

# 🌟 统一拦截器：把大模型按在地上摩擦，禁止它编造
def _format_err(msg: str) -> str:
    return f"【系统拦截】{msg}。你必须原样告诉用户底层数据异常，绝对禁止自己捏造任何价格、指标或话术！"

@tool
def query_moving_averages(ts_code: str) -> str:
    """计算 5/10/20 日均线及当前价格位置。"""
    try:
        if re.search(r'[\u4e00-\u9fa5]', ts_code): return _format_err("工具不支持中文，必须传入股票代码")
        df = pro.daily(ts_code=ts_code, limit=30).sort_values('trade_date').reset_index(drop=True)
        if df.empty or len(df) < 20: return _format_err("Tushare返回空数据，可能是无权限或代码错误")
        current_price = df.iloc[-1]['close']
        ma5, ma10, ma20 = [round(df['close'].rolling(window=w).mean().iloc[-1], 2) for w in [5, 10, 20]]
        res = f"【均线系统】当前价：{current_price}元\n- MA5: {ma5}元\n- MA10: {ma10}元\n- MA20: {ma20}元\n"
        return res + "请判断当前处于多头还是空头，以及是否跌破支撑位。"
    except Exception as e: return _format_err(f"计算异常: {str(e)}")

@tool
def query_yearly_high_low(ts_code: str) -> str:
    """测算近一年极值与当前回撤幅度。"""
    try:
        if re.search(r'[\u4e00-\u9fa5]', ts_code): return _format_err("工具不支持中文，必须传入股票代码")
        df = pro.daily(ts_code=ts_code, limit=250)
        if df.empty: return _format_err("Tushare返回历史数据为空")
        current_price = df.iloc[0]['close']
        high_price, low_price = df['high'].max(), df['low'].min()
        drawdown = round((current_price - high_price) / high_price * 100, 2)
        rebound = round((current_price - low_price) / low_price * 100, 2)
        return f"【近一年位置】当前价：{current_price}元\n- 最高价：{high_price}元 (回撤 {drawdown}%)\n- 最低价：{low_price}元 (反弹 +{rebound}%)"
    except Exception as e: return _format_err(f"极值计算异常: {str(e)}")

@tool
def query_volume_analysis(ts_code: str) -> str:
    """对比近日成交量，判定放量/缩量。"""
    try:
        if re.search(r'[\u4e00-\u9fa5]', ts_code): return _format_err("工具不支持中文，必须传入股票代码")
        df = pro.daily(ts_code=ts_code, limit=6)
        if df.empty or len(df) < 6: return _format_err("量能数据不足")
        today_vol = df.iloc[0]['vol']
        avg_5d_vol = df.iloc[1:6]['vol'].mean()
        ratio = round(today_vol / avg_5d_vol, 2)
        status = "放量" if ratio > 1.2 else ("缩量" if ratio < 0.8 else "平量")
        return f"【量能异动】今日成交量是过去5日均量的 {ratio} 倍，属于【{status}】状态。"
    except Exception as e: return _format_err(f"量能分析异常: {str(e)}")

@tool
def query_stock_recent_trend(ts_code: str) -> str:
    """查询股票近5日量价走势矩阵。"""
    try:
        if re.search(r'[\u4e00-\u9fa5]', ts_code): return _format_err("工具不支持中文，必须传入股票代码")
        df = pro.daily(ts_code=ts_code, limit=5).sort_values('trade_date')
        if df.empty: return _format_err("近期走势数据为空")
        trend_info = f"【{ts_code} 近5日量价】\n"
        for _, row in df.iterrows():
            trend_info += f"- {row['trade_date']}: 收盘 {row['close']}元, 涨跌 {row['pct_chg']}%, 成交额 {round(row['amount'] / 10000, 2)}亿元\n"
        return trend_info
    except Exception as e: return _format_err(f"走势查询异常: {str(e)}")

CURRENT_MODEL = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
chat_llm = ChatOpenAI(model=CURRENT_MODEL, temperature=0)

TECHNICAL_PROMPT = """你是一个杀伐果断、信奉“量价即一切”的短线游资。

【核心沟通准则】
1. 必须调用专属工具获取数据，绝不凭空捏造。
2. ⚠️ 【致命红线】：如果工具返回【系统拦截】或异常，你必须原样告诉用户“底层接口获取失败”，绝对禁止擅自瞎编任何股价、均线或走势！
3. 说人话：像营业部老操盘手一样直接给出干脆的判断。
4. 绝对禁止使用 Emoji 或 Markdown 特殊符号。"""

tech_agent = create_react_agent(
    chat_llm,
    tools=[query_moving_averages, query_yearly_high_low, query_volume_analysis, query_stock_recent_trend, query_realtime_price, query_stock_fund_flow]
)