# data_sync/sync_daily.py
import asyncio
import logging
import pandas as pd
from data_sync.tushare_client import pro
from core.db_manager import mongo_manager

logger = logging.getLogger("sync_daily")


async def sync_daily_data(ts_code: str):
    logger.info(f"开始从 Tushare 获取 {ts_code} 的日线数据...")
    try:
        # 使用 to_thread 防止网络请求阻塞 FastAPI 主线程
        df = await asyncio.to_thread(pro.daily, ts_code=ts_code)

        if df is None or df.empty:
            logger.warning(f"未获取到 {ts_code} 的数据")
            return False

        # 【关键防错】：把所有 NaN 替换成 None，防止 MongoDB 报错！
        df = df.where(pd.notnull(df), None)

        data_list = df.to_dict(orient='records')

        collection = mongo_manager.db["stock_daily"]

        # 工业级做法：不是删了重插，而是针对当天的日期进行 Upsert (存在则更新，不存在则插入)
        # 这里为了简便，暂时保留你的全量替换逻辑，但更推荐后续改成增量更新
        await collection.delete_many({"ts_code": ts_code})
        await collection.insert_many(data_list)

        logger.info(f"✅ 成功将 {ts_code} 的 {len(data_list)} 条日线记录存入数据库！")
        return True
    except Exception as e:
        logger.error(f"❌ {ts_code} 获取失败: {e}")
        return False

# 删除了底部的 if __name__ == "__main__": 测试代码，让它纯粹作为一个被调用的功能函数。