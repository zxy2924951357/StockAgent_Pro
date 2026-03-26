# tools/get_screener.py
import logging
import pandas as pd
import tushare as ts
import os
from langchain_core.tools import tool
from core.db_manager import mongo_manager

logger = logging.getLogger("tools_screener")


@tool
async def tool_multi_factor_screening() -> str:
    """
    【量化选股神器】当用户要求“推荐股票”、“帮我选股”、“找一些好票”、“有什么潜力股”时必须调用此工具！
    它会根据量化多因子模型（价值估值+高动量活跃度），从全市场扫描出当前最值得关注的潜力标的。
    """
    try:
        # 1. 尝试从本地数据库获取基础股票池（包含名字和行业）
        cursor = mongo_manager.db["stock_basic"].find({}, {"ts_code": 1, "name": 1, "industry": 1, "_id": 0})
        stocks = await cursor.to_list(length=None)
        base_df = pd.DataFrame(stocks)
        if not base_df.empty and 'name' in base_df.columns:
            base_df = base_df[~base_df['name'].str.contains('ST')]  # 剔除 ST 股

        # 2. 初始化 Tushare 拉取全市场最新量价估值
        ts_token = os.getenv("TUSHARE_TOKEN", "")
        if not ts_token:
            return "系统未配置 Tushare Token，选股引擎无法获取最新估值数据。"

        pro = ts.pro_api(ts_token)
        df_val = pro.daily_basic(ts_code='', trade_date='', fields='ts_code,pe,turnover_rate,total_mv')
        if df_val.empty:
            return "未能从数据源获取到最新估值数据。"

        # 3. 核心量化过滤：估值合理 (PE 10-35) 且 流动性好 (市值>50亿)
        filtered = df_val[(df_val['pe'] > 10) & (df_val['pe'] < 35) & (df_val['total_mv'] > 500000)]

        # 4. 合并股票名称与行业
        if not base_df.empty:
            result_df = pd.merge(filtered, base_df, on='ts_code', how='inner')
        else:
            result_df = filtered
            result_df['name'] = result_df['ts_code']
            result_df['industry'] = '未知'

        if result_df.empty:
            return "当前市场无满足苛刻多因子条件的标的。"

        # 5. 因子打分排序 (动量+价值双轮驱动)
        result_df['pe_score'] = result_df['pe'].rank(ascending=True)  # PE越低分越高
        result_df['turnover_score'] = result_df['turnover_rate'].rank(ascending=False)  # 换手越高分越高

        # 综合打分：动量占60%，估值占40%
        result_df['total_score'] = result_df['pe_score'] * 0.4 + result_df['turnover_score'] * 0.6

        # 6. 提取 Top 5 最优标的
        top_stocks = result_df.sort_values('total_score').head(5)

        res = "【多因子量化选股池 (Top 5 潜力标的)】\n"
        for _, row in top_stocks.iterrows():
            res += f"- {row['name']} ({row['ts_code']}) | 所属行业: {row['industry']} | 动态PE: {row['pe']} | 换手率: {row['turnover_rate']}%\n"

        res += "\n【执行建议】：请向客户展示上述初筛名单，并根据当前的宏观热点，挑选出 1-2 只进行重点点评推荐。"
        return res

    except Exception as e:
        logger.error(f"多因子打分系统崩溃: {e}")
        return "选股引擎暂时离线，请稍后再试。"