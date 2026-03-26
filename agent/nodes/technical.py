# agent/nodes/technical.py
import logging
from agent.state import AgentState
from langchain_core.messages import HumanMessage
from agent.technical import tech_agent  # 引入我们配好工具的打工仔

logger = logging.getLogger("node_technical")


async def technical_node(state: AgentState):
    ts_code = state.get("ts_code", "")
    stock_name = state.get("stock_name", "")
    image_base64 = (state.get("image_base64", "") or "").strip()

    logger.info(f"==> 📈 技术面团队进场: 准备分析 {stock_name}({ts_code})")

    # 🚀 强制注入 ts_code；若检测到图像则启用图文共振分析
    query = f"你现在必须使用你的专属工具，查询【{stock_name}】(标准股票代码：{ts_code}) 的均线系统、近一年高低点和主力资金流向。请给出详细的文字分析。"

    try:
        message_content = query
        if image_base64:
            image_url = image_base64 if image_base64.startswith("data:image") else f"data:image/jpeg;base64,{image_base64}"
            message_content = [
                {"type": "text", "text": query + " 用户已上传K线截图，请先做图像结构识别，再与工具数据交叉验证。"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
            logger.info("🖼️ 技术面节点检测到截图，已启用图文共振输入。")

        res = await tech_agent.ainvoke({"messages": [HumanMessage(content=message_content)]})
        return {"technical_res": res["messages"][-1].content}
    except Exception as e:
        logger.error(f"❌ 技术面分析失败: {e}")
        return {"technical_res": "技术面数据获取失败。"}