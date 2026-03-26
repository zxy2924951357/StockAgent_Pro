# tools/get_news.py
import logging
import akshare as ak
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

logger = logging.getLogger("tool_news")


# ==========================================
# 1. 保留你原有的：个股新闻查询
# ==========================================
@tool
async def get_news_sentiment(stock_code: str) -> str:
    """
    获取指定股票的最新真实新闻
    当用户问某只具体股票的“最新消息”、“有什么新闻”、“舆情”时调用此工具。
    :param stock_code: 股票代码，如 "600519.SH" 或 "600519"
    """
    logger.info(f"工具调用: 获取 {stock_code} 的近期真实新闻舆情")

    try:
        symbol = stock_code.split('.')[0]
        news_df = ak.stock_news_em(symbol=symbol)

        if news_df.empty:
            return "近期暂无相关新闻。"

        recent_news = news_df.head(5)
        news_summary = ""
        for index, row in recent_news.iterrows():
            news_summary += f"【{row['发布时间']}】{row['新闻标题']}\n"
            news_summary += f"摘要：{row['新闻内容']}\n\n"

        return news_summary

    except Exception as e:
        logger.error(f"获取新闻失败: {e}")
        return "获取新闻数据失败，请根据市场盘面情绪进行推测。"


# ==========================================
# 2. 移植新增的：全网宏观多元新闻聚合
# ==========================================
@tool
async def tool_get_macro_hotspots() -> str:
    """
    【全网舆情与宏观聚合器】当用户问“今天有什么大新闻”、“大盘消息”、“宏观面有什么异动”、“聚合资讯”时必须调用此工具。
    它会自动扫描全网权威财经媒体的实时快讯，并由内部AI引擎实时聚类提炼出最重要的宏观事件和对应利好板块。
    """
    try:
        # 1. 使用 AkShare 获取财联社最新电报快讯
        df = ak.stock_telegraph_cls()
        if df.empty:
            return "暂无最新市场快讯。"

        recent_news = df.head(40)  # 取最近40条快讯
        news_text = ""
        for _, row in recent_news.iterrows():
            if len(str(row['内容'])) > 20:  # 过滤太短的废话
                news_text += f"[{row['发布时间']}] {row['内容']}\n"

        if not news_text:
            return "当前抓取到的快讯内容为空。"

        # 2. 呼叫大模型进行【去重与聚类提炼】
        current_model = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
        llm = ChatOpenAI(model=current_model, temperature=0.1)

        sys_prompt = """你现在是顶级券商的宏观策略总监。
下面是一堆过去几小时内密集的、碎片化的市场快讯电报。
你的任务是：
1. 【去重与聚合】：将说同一件事（如同一个政策发布、同一个产业突发）的新闻合并。
2. 【提炼主线】：从中提炼出对A股市场影响最大的 3 到 4 条核心宏观/产业事件。
3. 【明确利好】：对每个事件，必须用一句话明确指出它利好哪个【具体的行业板块】。
4. 【格式要求】：用清晰的 Markdown 列表输出，语言风格像资深基金经理的晨会/晚间纪要，拒绝废话。"""

        human_prompt = f"请提炼以下原始电报内容：\n\n{news_text}"

        logger.info("🚀 正在调用大模型进行实时多元新闻聚合提炼...")
        res = await llm.ainvoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=human_prompt)
        ])

        return res.content

    except Exception as e:
        logger.error(f"新闻聚合提炼失败: {e}")
        return "新闻聚合引擎分析异常，请检查网络或数据源接口。"