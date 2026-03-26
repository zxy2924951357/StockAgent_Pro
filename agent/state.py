# agent/state.py
from typing import TypedDict, Optional


class AgentState(TypedDict):
    ts_code: str
    stock_name: str
    image_base64: Optional[str]  # 可选的用户上传图像（base64/data URL）

    # === 各个专员的输出产物 ===
    fundamental_res: Optional[str]  # 基本面分析结果 (Tushare 真实数据注入点)
    technical_res: Optional[str]  # 技术面分析结果 (K线特征注入点)
    sentiment_res: Optional[str]  # 情绪面/舆情分析结果

    # === 统稿与审核机制 ===
    final_report: Optional[str]  # Supervisor 审核通过后的最终研报
    critique: Optional[str]  # Supervisor 给出的修改意见（打回重写时用到）
    retry_count: int  # 重试次数（控制循环边界，防止无限死循环）
    backtest_summary: Optional[str]  # 回测摘要（用于附录与调试）