# agent/nodes/sentiment.py
import logging
from agent.state import AgentState
from tools.get_news import get_news_sentiment
from core.llm_manager import llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("node_sentiment")


async def sentiment_node(state: AgentState):
    ts_code = state.get("ts_code", "")
    stock_name = state.get("stock_name", "")
    critique = state.get("critique", "")

    logger.info(f"==> 🕵️‍♂️ 舆情风控专员进场: 开始对 {stock_name} 进行全网扫雷")

    # `get_news_sentiment` 是由 @tool 装饰后的 StructuredTool，必须用 .ainvoke 调用
    news_data = await get_news_sentiment.ainvoke({"stock_code": ts_code})

    # 容错处理
    if not news_data:
        logger.warning(f"⚠️ 未获取到 {stock_name} 的有效舆情数据。")
        news_data = "近期全网暂无关于该标的的重大舆情、公告或新闻资讯。"

    sys_prompt = """你是一个冷酷无情、极度专业的市场风控与舆情分析专家。
你的任务是从新闻资讯中敏锐地嗅出潜在风险或资金炒作的情绪，并进行客观定性。

【铁律：违反将被立即开除】
1. 你的分析必须且只能基于下方 <NEWS_DATA> 提供的内容，绝不可动用大模型记忆脑补未发生的新闻。
2. 语言必须客观、书面化、专业化（例如使用“资金风险偏好”、“情绪溢价”、“避险情绪”等金融投研词汇）。
3. 绝对严禁使用任何 Emoji（如 ✅, ❌, ⚠️, 🚨, 📌 等），直接输出连贯的中文段落。
4. 每一项重要的舆情或事件结论，必须在句末标注 [来源: 舆情监控]。
5. 永远不要提供买卖建议，你只负责提示当前的情绪温度和潜在黑天鹅风险。"""

    human_prompt = f"分析标的：{stock_name} ({ts_code})\n\n<NEWS_DATA>\n{news_data}\n</NEWS_DATA>"

    if critique:
        logger.warning(f"⚠️ 舆情节点收到风控审查员(Supervisor)打回意见，触发重写！")
        human_prompt += f"\n\n====================\n【投资总监的严厉驳回意见】\n{critique}\n\n请你深刻反思，严格遵循无Emoji、纯客观书面语的铁律，重新撰写舆情风控段落！"

    try:
        response = await llm.ainvoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=human_prompt)
        ])
        return {"sentiment_res": response.content}
    except Exception as e:
        logger.error(f"❌ 舆情分析失败: {e}")
        return {"sentiment_res": "舆情模型临时不可用，当前仅保留基础风险提示：请关注公告与成交量异常波动。"}