# tools/get_financial.py
import os
import tushare as ts
from datetime import datetime, timedelta

pro = ts.pro_api(os.getenv("TUSHARE_TOKEN", ""))


async def get_financial_indicator(ts_code: str) -> str:
    """获取基本面财务指标"""
    try:
        # 获取过去一年的数据，确保绝不会返回空
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        df = pro.fina_indicator(ts_code=ts_code, start_date=start_date)

        if df.empty:
            return "暂未查到最新财报数据。"

        # 按报告期倒序，取最新的一期
        df = df.sort_values('end_date', ascending=False)
        row = df.iloc[0]

        res = f"最新财报期: {row.get('end_date')}\n"
        res += f"- 扣非净利润同比增长: {row.get('dt_netprofit_yoy', '未知')}%\n"
        res += f"- 毛利率: {row.get('grossprofit_margin', '未知')}%\n"
        res += f"- ROE(净资产收益率): {row.get('roe', '未知')}%\n"
        return res

    except Exception as e:
        return f"财务数据获取异常: {e}"