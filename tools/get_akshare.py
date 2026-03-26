# tools/get_akshare.py
import akshare as ak
import logging
from langchain_core.tools import tool

logger = logging.getLogger("akshare_tools")


@tool
def query_stock_fund_flow(ts_code: str) -> str:
    """
    【技术面/游资专属工具】查询个股近期的主力资金流向。
    当用户问“主力在买还是卖”、“资金流向”、“有大资金进场吗”时调用。
    """
    try:
        # 转换代码格式：000001.SZ -> 000001
        symbol = ts_code.split('.')[0]
        # 获取东方财富个股主力资金流向
        df = ak.stock_individual_fund_flow(stock=symbol, market="sh" if "SH" in ts_code else "sz")

        if df.empty:
            return "未获取到该股的资金流向数据。"

        # 取最近的一条数据
        latest = df.iloc[0]
        res = f"【资金面监控】个股：{ts_code}\n"
        res += f"- 主力净流入: {latest.get('主力净流入-净额', '未知')}元\n"
        res += f"- 超大单净流入: {latest.get('超大单净流入-净额', '未知')}元\n"
        res += f"- 大单净流入: {latest.get('大单净流入-净额', '未知')}元\n"
        res += f"分析提示：超大单和大单代表机构或游资态度，请据此判断是否有大资金介入。"
        return res
    except Exception as e:
        logger.error(f"AKShare 资金流向获取失败: {e}")
        return "资金流向数据接口暂不可用。"


@tool
def query_realtime_hot_concepts() -> str:
    """
    【宏观策略师专属工具】查询当前市场实时领涨的题材概念。
    当用户问“现在大盘在炒什么”、“今天什么概念最火”时调用。
    """
    try:
        df = ak.stock_board_concept_name_em()
        if df.empty: return "未获取到概念板块数据。"

        # 提取涨幅前 5 的板块
        top_5 = df.head(5)
        res = "【实时资金猛攻题材 (Top 5)】\n"
        for _, row in top_5.iterrows():
            res += f"- {row['板块名称']}: 整体涨幅 {row['涨跌幅']}%, 领涨股: {row['领涨股票']}\n"
        return res
    except Exception as e:
        logger.error(f"AKShare 题材获取失败: {e}")
        return "实时题材接口暂不可用。"