# agent/nodes/fundamental.py
import logging
from agent.state import AgentState
from langchain_core.messages import HumanMessage
from agent.fundamental import fund_agent  # 引入我们配好工具的打工仔

logger = logging.getLogger("node_fundamental")


async def fundamental_node(state: AgentState):
    ts_code = state.get("ts_code", "")
    stock_name = state.get("stock_name", "")

    logger.info(f"==> 🏢 基本面团队进场: 准备分析 {stock_name}({ts_code})")

    # 🚀 终极杀手锏 + 双重防幻觉锁：强行把正确的代码拼接到提示词里，并在任务执行前最后一次重申纪律！
    query = f"""你现在必须使用你的专属工具，查询【{stock_name}】(标准股票代码：{ts_code}) 的基本面、估值和财务排雷数据。请给出详细的文字分析。

    【🔴 最终行动指令与纪律重申】：
    请牢记你的系统纪律：如果没有查到最新财报数据，请务必直接坦白说明“暂无数据，略过此项排雷”，绝对禁止动用你的知识库进行任何形式的瞎编、推演或猜测！"""

    try:
        # 把强行拼接好的带有威慑力的指令喂给大模型
        res = await fund_agent.ainvoke({"messages": [HumanMessage(content=query)]})
        return {"fundamental_res": res["messages"][-1].content}
    except Exception as e:
        logger.error(f"❌ 基本面分析失败: {e}")
        return {"fundamental_res": "由于底层接口网络异常，基本面数据获取失败。"}