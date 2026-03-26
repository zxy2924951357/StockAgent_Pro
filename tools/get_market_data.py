# tools/get_market_data.py
import logging
from core.db_manager import mongo_manager
from data_sync.sync_daily import sync_daily_data

logger = logging.getLogger("tool_market_data")


async def get_stock_daily(ts_code: str, limit: int = 30) -> str:
    """
    获取股票近期的日线数据（带有按需拉取机制）
    """
    logger.info(f"工具调用: 尝试获取 {ts_code} 的日线数据")
    collection = mongo_manager.db["stock_daily"]

    # 1. 查本地
    cursor = collection.find({"ts_code": ts_code}).sort("trade_date", -1).limit(limit)
    data = await cursor.to_list(length=limit)

    # 2. 没数据就当场下载
    if not data:
        logger.warning(f"⚠️ 本地无 {ts_code} 的日线数据，触发按需拉取...")
        try:
            await sync_daily_data(ts_code)

            cursor = collection.find({"ts_code": ts_code}).sort("trade_date", -1).limit(limit)
            data = await cursor.to_list(length=limit)

            if not data:
                return ""
        except Exception as e:
            logger.error(f"❌ 按需拉取日线数据失败: {e}")
            return ""

    # 3. 格式化输出
    result_str = "交易日期 | 开盘 | 收盘 | 最高 | 最低 | 涨跌幅(%)\n"
    result_str += "-" * 50 + "\n"
    for item in data:
        date = item.get("trade_date", "")
        o = item.get("open", 0)
        c = item.get("close", 0)
        h = item.get("high", 0)
        l = item.get("low", 0)
        pct = item.get("pct_chg", 0)
        result_str += f"{date} | {o} | {c} | {h} | {l} | {pct}\n"

    return result_str