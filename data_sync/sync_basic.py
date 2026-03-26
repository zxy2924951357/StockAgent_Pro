# data_sync/sync_basic.py
import asyncio
import logging
import pandas as pd
from data_sync.tushare_client import pro
from core.db_manager import mongo_manager

logger = logging.getLogger("sync_basic")


async def sync_stock_basic():
    logger.info("开始从 Tushare 获取全市场基础名录...")
    try:
        # 获取上市状态为 L (上市) 的所有股票
        df = await asyncio.to_thread(pro.stock_basic, exchange='', list_status='L',
                                     fields='ts_code,symbol,name,area,industry,list_date')

        if df is None or df.empty:
            logger.warning("未获取到基础名录数据")
            return False

        # 清洗 NaN 防报错
        df = df.where(pd.notnull(df), None)
        data_list = df.to_dict(orient='records')

        collection = mongo_manager.db["stock_basic"]
        # 名录数据量不大（约5000条），全量替换最干净
        await collection.delete_many({})
        await collection.insert_many(data_list)

        logger.info(f"✅ 成功同步 {len(data_list)} 条股票基础信息！")
        return True
    except Exception as e:
        logger.error(f"❌ 基础信息获取失败: {e}")
        return False