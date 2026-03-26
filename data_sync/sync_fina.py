# data_sync/sync_fina.py
import asyncio
import logging
import pandas as pd
import tushare as ts
from core.config import config
from core.db_manager import mongo_manager

logger = logging.getLogger("sync_fina")


async def sync_financial_data(ts_code: str):
    """
    从 Tushare 拉取指定股票的财务指标并存入 MongoDB
    """
    logger.info(f"开始从 Tushare 拉取 {ts_code} 的财务数据...")

    # 初始化 Tushare API
    ts.set_token(config.TUSHARE_TOKEN)
    pro = ts.pro_api()

    try:
        # 使用 to_thread 防止网络请求阻塞 FastAPI 主线程
        df = await asyncio.to_thread(pro.fina_indicator, ts_code=ts_code)

        if df is None or df.empty:
            logger.warning(f"⚠️ Tushare 未返回 {ts_code} 的财务数据。可能是刚上市或触发限流。")
            return False

        # 【关键防错清洗】：将 Pandas 的 NaN/NaT 全部替换为 Python 的 None，防 MongoDB 报错
        df = df.where(pd.notnull(df), None)

        # 转换为字典列表
        data_list = df.to_dict(orient='records')

        # 存入本地数据库
        collection = mongo_manager.db["fina_indicator"]

        # 创建复合唯一索引，防止以后重复插入同一天的财报（即使多次运行脚本也是安全的）
        await collection.create_index([("ts_code", 1), ("end_date", -1)], unique=True)

        # 工业级做法：使用 upsert (存在则更新，不存在则插入)
        success_count = 0
        for item in data_list:
            result = await collection.update_one(
                {"ts_code": item["ts_code"], "end_date": item["end_date"]},
                {"$set": item},
                upsert=True
            )
            if result.upserted_id or result.modified_count > 0:
                success_count += 1

        logger.info(f"✅ 成功将 {ts_code} 的 {success_count} 条财务记录安全存入 MongoDB！")
        return True

    except Exception as e:
        logger.error(f"❌ 同步 {ts_code} 财务数据彻底失败: {e}")
        return False

# 已经彻底移除了底部的 if __name__ == "__main__": 测试代码
# 现在的 sync_fina.py 是一个纯净的被调用模块，完全服务于：
# 1. FastAPI 里的定时自动调度 (APScheduler)
# 2. Agent 工具里的按需实时拉取 (On-demand Fetch)