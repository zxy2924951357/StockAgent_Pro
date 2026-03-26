import os
import asyncio
import pandas as pd
import tushare as ts
from datetime import datetime
from dotenv import load_dotenv

# 引入你现有的 MongoDB 管理器
from core.db_manager import mongo_manager

# 初始化环境变量与 Tushare
load_dotenv()
ts.set_token(os.getenv("TUSHARE_TOKEN", ""))
pro = ts.pro_api()


async def sync_trend_stocks():
    """
    【每日选股引擎】
    扫描全市场股票，筛选出同时满足：
    1. 均线多头排列 (收盘价 > MA5 > MA10 > MA20)
    2. 强势放量 (今日成交量 > 过去5日均量 1.5倍)
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⚙️ 选股引擎启动：开始扫描全市场多头放量标的...")

    try:
        # 1. 获取最近 30 个交易日的日历 (为了计算 20 日均线，至少需要 20 天以上的数据)
        cal = pro.trade_cal(exchange='SSE', is_open='1', end_date=datetime.now().strftime('%Y%m%d'), limit=30)
        trade_dates = cal['cal_date'].tolist()

        if not trade_dates:
            print("❌ 未获取到交易日历。")
            return

        start_date = trade_dates[-1]  # 30个交易日前的日期
        end_date = trade_dates[0]  # 最近的交易日

        # 2. 一次性拉取全市场这 30 天的日线数据 (Pandas 处理十几万行数据极快)
        print("📥 正在从 Tushare 提取全市场近期行情数据...")
        df = pro.daily(start_date=start_date, end_date=end_date)

        if df.empty:
            print("⚠️ 未获取到行情数据。")
            return

        # 按时间正序排列，方便计算均线
        df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

        print("🧠 正在进行矩阵运算与因子过滤...")
        # 3. 分组计算技术指标
        df['MA5'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(window=5).mean())
        df['MA10'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(window=10).mean())
        df['MA20'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(window=20).mean())
        df['VOL_MA5'] = df.groupby('ts_code')['vol'].transform(lambda x: x.rolling(window=5).mean())

        # 4. 只截取全市场最新一天的数据截面
        latest_date = df['trade_date'].max()
        today_df = df[df['trade_date'] == latest_date].copy()

        # 5. 核心选股逻辑 (布尔索引过滤)
        # 条件 A: 均线多头
        cond_trend = (today_df['close'] > today_df['MA5']) & \
                     (today_df['MA5'] > today_df['MA10']) & \
                     (today_df['MA10'] > today_df['MA20'])

        # 条件 B: 资金爆量 (成交量大于 5日均量 1.5倍)
        cond_volume = today_df['vol'] > (today_df['VOL_MA5'] * 1.5)

        # 条件 C: 剔除 ST 股或停牌股 (可以通过涨跌幅或交易状态辅助，这里简单过滤无量股)
        cond_active = today_df['vol'] > 0

        # 合并条件得到最终标的
        bull_stocks = today_df[cond_trend & cond_volume & cond_active].copy()

        # 6. 数据清洗与入库
        target_count = len(bull_stocks)
        print(f"🎯 筛选完毕！今日 ({latest_date}) 共发现 {target_count} 只强势异动股。")

        if target_count > 0:
            # 格式化准备入库的数据
            records = bull_stocks[['ts_code', 'close', 'pct_chg', 'vol']].to_dict('records')

            # 关联上股票名称 (去 stock_basic 表里查名字)
            for item in records:
                basic = await mongo_manager.db["stock_basic"].find_one({"ts_code": item["ts_code"]})
                item["name"] = basic.get("name", "未知") if basic else "未知"
                item["scan_date"] = latest_date
                item["reason"] = "均线多头且放量突破 (vol > 1.5*MA5)"

            # 清空旧的预警池，插入最新一期的金股
            await mongo_manager.db["trend_alerts"].delete_many({})
            await mongo_manager.db["trend_alerts"].insert_many(records)
            print("✅ 强势股池已成功同步至 MongoDB [trend_alerts] 集合！")
        else:
            print("📉 今日市场情绪低迷，未扫描到符合条件的强势股。")

    except Exception as e:
        print(f"❌ 选股引擎执行异常: {e}")

# 如果想单独测试这个脚本，取消下面的注释运行即可
# if __name__ == "__main__":
#     asyncio.run(sync_trend_stocks())