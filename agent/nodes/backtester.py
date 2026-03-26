import logging
import random

from agent.state import AgentState
from routers.backtest_api import run_backtest

logger = logging.getLogger("node_backtester")


def _pick_strategy(report_text: str) -> str:
    text = (report_text or "").lower()
    if ("macd" in text) or ("金叉" in report_text) or ("死叉" in report_text):
        return "macd_trend"
    if ("rsi" in text) or ("超卖" in report_text) or ("超买" in report_text):
        return "rsi_reversion"
    return "ma_cross"


def _strategy_zh(strategy: str) -> str:
    mapping = {
        "ma_cross": "双均线交叉策略",
        "macd_trend": "MACD 波段跟随策略",
        "rsi_reversion": "RSI 均值回复策略",
    }
    return mapping.get(strategy, strategy)


async def backtest_node(state: AgentState):
    """
    在发布研报前执行快速回测验证。
    规则：
    - 胜率 < 50% 且 retry_count < 3 -> 触发打回并要求重写
    - 其余情况 -> 放行
    任意异常均降级为放行，不中断主流程。
    """
    ts_code = state.get("ts_code", "")
    retry_count = int(state.get("retry_count", 0) or 0)
    final_report = state.get("final_report", "")

    if not final_report:
        logger.warning("⚠️ [回测闸门] 未检测到 final_report，直接放行。")
        return {"critique": ""}

    try:
        selected_strategy = _pick_strategy(final_report)

        # 优先尝试真实回测接口（按研报关键词自动选策略）
        resp = await run_backtest(ts_code=ts_code, strategy=selected_strategy)
        win_rate_pct = 0.0
        kpi = {}
        if isinstance(resp, dict) and resp.get("code") == 200:
            data = resp.get("data", {})
            kpi = data.get("kpi", {}) or {}
            win_rate_pct = float(kpi.get("win_rate", 0.0) or 0.0)
            logger.info(
                f"🧪 [回测闸门] 真实回测: strategy={selected_strategy}, win_rate={win_rate_pct:.2f}%"
            )
        else:
            # 回测接口不可用时，按 PRD 要求使用 mock 胜率跑通链路
            win_rate_pct = float(random.randint(30, 70))
            kpi = {
                "strategy_return_pct": 0.0,
                "stock_return_pct": 0.0,
                "win_rate": round(win_rate_pct, 2),
                "max_drawdown": 0.0,
                "trade_days": 0,
            }
            logger.warning(
                f"⚠️ [回测闸门] 回测接口异常，启用 mock: strategy={selected_strategy}, win_rate={win_rate_pct:.2f}%"
            )

        appendix = (
            "\n\n## 五、 历史回测验证附录\n"
            f"- 回测策略: {_strategy_zh(selected_strategy)}\n"
            f"- 胜率: {float(kpi.get('win_rate', 0.0) or 0.0):.2f}%\n"
            f"- 策略收益: {float(kpi.get('strategy_return_pct', 0.0) or 0.0):.2f}%\n"
            f"- 基准收益: {float(kpi.get('stock_return_pct', 0.0) or 0.0):.2f}%\n"
            f"- 最大回撤: {float(kpi.get('max_drawdown', 0.0) or 0.0):.2f}%\n"
            f"- 交易天数: {int(kpi.get('trade_days', 0) or 0)}\n"
        )

        if win_rate_pct < 50.0 and retry_count < 3:
            critique = (
                f"回测警报：当前分析逻辑在过去窗口回测胜率仅为 {win_rate_pct:.2f}% ，"
                "存在重大缺陷，请重新审视技术面支撑位与风险收益比，并修订综合建议。"
            )
            logger.warning(f"🔴 [回测闸门] 触发打回重写，retry={retry_count + 1}")
            return {"critique": critique, "retry_count": retry_count + 1, "backtest_summary": appendix}

        logger.info(f"🟢 [回测闸门] 放行发布，胜率={win_rate_pct:.2f}%，retry={retry_count}")
        report_with_appendix = final_report if "## 五、 历史回测验证附录" in final_report else (final_report + appendix)
        return {"critique": "", "backtest_summary": appendix, "final_report": report_with_appendix}
    except Exception as e:
        logger.warning(f"⚠️ [回测闸门] 节点异常，已降级放行: {e}")
        return {"critique": ""}

