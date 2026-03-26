# agent/graph.py
import logging
from langgraph.graph import StateGraph, START, END

from agent.state import AgentState
from agent.nodes.fundamental import fundamental_node
from agent.nodes.technical import technical_node
from agent.nodes.sentiment import sentiment_node
from agent.nodes.supervisor import supervisor_node
from agent.nodes.backtester import backtest_node

logger = logging.getLogger("stock_report_graph")

# 初始化状态图
workflow = StateGraph(AgentState)

# 注册所有分析节点
workflow.add_node("fundamental", fundamental_node)
workflow.add_node("technical", technical_node)
workflow.add_node("sentiment", sentiment_node)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("backtester", backtest_node)

# 构建流水线：基本面 -> 技术面 -> 情绪面 -> 总监审核
workflow.add_edge(START, "fundamental")
workflow.add_edge("fundamental", "technical")
workflow.add_edge("technical", "sentiment")
workflow.add_edge("sentiment", "supervisor")
workflow.add_edge("supervisor", "backtester")


def should_publish(state: AgentState) -> str:
    """
    回测闸门逻辑：
    - critique 非空且 retry_count < 3 -> 回流 supervisor 重写
    - 其余情况 -> 发布
    """
    critique = (state.get("critique") or "").strip()
    retry_count = int(state.get("retry_count", 0) or 0)
    if critique and retry_count < 3:
        logger.warning(f"🔴 [路由] 回测未通过，流转回 supervisor 重写。retry={retry_count}")
        return "rewrite"
    logger.info("🟢 [路由] 回测通过或达到重试上限，发布最终研报。")
    return "publish"


# 添加条件分支：回测不通过则重写，通过则结束
workflow.add_conditional_edges(
    "backtester",
    should_publish,
    {
        "publish": END,
        "rewrite": "supervisor"
    }
)

stock_agent_app = workflow.compile()
logger.info("✅ 深度研报工作流 (Deep Report Graph) 编译完成！合规路由已就绪。")