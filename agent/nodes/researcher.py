# agent/nodes/researcher.py
import logging
from agent.state import AgentState

logger = logging.getLogger("node_researcher")


async def research_node(state: AgentState):
    """
    状态重置与熔断节点 (Data Reset Node)
    当风控审查组长 (Supervisor) 打回研报时，此节点被激活。
    核心职责：把上一轮生成的不合规草稿全部“物理销毁”，
    强制底层的分析师团队带着组长最新的 critique (批评) 重新调研和撰写。
    """
    critique = state.get('critique', '未提供具体打回原因')
    current_retry = state.get('retry_count', 0)

    logger.warning(f"🚨 [风控熔断触发] 收到组长的严厉驳回指令！(当前重试次数: {current_retry})")
    logger.warning(f"📄 驳回原因: {critique}")
    logger.info(f"🗑️ 正在撕毁被污染的研报草稿，清空上下文缓存...")

    # 安全锁：重试次数 +1
    next_retry_count = current_retry + 1

    # 状态覆盖：清空三大分析师的输出，保证下一轮是一张白纸
    return {
        "fundamental_res": "",
        "technical_res": "",
        "sentiment_res": "",
        "retry_count": next_retry_count
    }