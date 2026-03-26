# core/db_manager.py
import motor.motor_asyncio
from core.config import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_manager")

class MongoManager:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_URI)
        self.db = self.client[config.MONGO_DB_NAME]
        logger.info(f"成功连接到 MongoDB 数据库: {config.MONGO_DB_NAME}")

    async def insert_many(self, collection_name: str, documents: list):
        """批量插入数据"""
        if not documents:
            return
        collection = self.db[collection_name]
        # 为了避免重复插入，这里简单处理，实际项目中通常用 update_one 的 upsert 操作
        await collection.delete_many({}) # 每次全量同步前先清空旧数据
        result = await collection.insert_many(documents)
        logger.info(f"集合 {collection_name} 成功插入 {len(result.inserted_ids)} 条数据")

    async def find_one(self, collection_name: str, query: dict):
        """查询单条数据"""
        collection = self.db[collection_name]
        return await collection.find_one(query)

# 实例化单例供全局使用
mongo_manager = MongoManager()