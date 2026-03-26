import os
import tushare as ts
import asyncio
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# 初始化 Tushare
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
if TUSHARE_TOKEN:
    ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def _fetch_fundamental_sync(ts_code: str):
    """同步获取基本面和资金流向数据"""
    try:
        # 1. 获取每日基本面指标 (PE, PB, 总市值, 流通市值, 换手率)
        # 注意：Tushare 的 ts_code 格式为 "002281.SZ" 或 "600519.SH"
        df_basic = pro.daily_basic(ts_code=ts_code, limit=1)

        # 2. 获取单日主力资金流向 (需要一定积分，如果权限不够这里可能返回空)
        df_moneyflow = pro.moneyflow(ts_code=ts_code, limit=1)

        result = {}
        if not df_basic.empty:
            result['pe_ttm'] = df_basic.iloc[0]['pe_ttm']  # 滚动市盈率
            result['pb'] = df_basic.iloc[0]['pb']  # 市净率
            result['total_mv'] = round(df_basic.iloc[0]['total_mv'] / 10000, 2)  # 总市值(亿元)
            result['turnover_rate'] = df_basic.iloc[0]['turnover_rate']  # 换手率
            result['turnover_rate_f'] = df_basic.iloc[0]['turnover_rate_f']  # 自由流通换手率

        if not df_moneyflow.empty:
            # 净流入 = (特大单买+大单买) - (特大单卖+大单卖)
            net_inflow = (df_moneyflow.iloc[0]['buy_elg_vol'] + df_moneyflow.iloc[0]['buy_lrg_vol']) - \
                         (df_moneyflow.iloc[0]['sell_elg_vol'] + df_moneyflow.iloc[0]['sell_lrg_vol'])
            result['net_main_inflow'] = net_inflow  # 主力净流入(手)
        else:
            result['net_main_inflow'] = "暂无数据(可能权限不足)"

        return result
    except Exception as e:
        print(f"❌ Tushare 抓取异常: {e}")
        return {}


async def get_stock_fundamentals(ts_code: str) -> dict:
    """供 LangGraph 调用的异步包装函数"""
    return await asyncio.to_thread(_fetch_fundamental_sync, ts_code)


# 测试代码
if __name__ == "__main__":
    import asyncio

    res = asyncio.run(get_stock_fundamentals("002281.SZ"))  # 测一下光迅科技
    print("基本面数据:", res)