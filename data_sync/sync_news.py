# data_sync/sync_news.py
import os
import tushare as ts
import asyncio
import logging
from datetime import datetime, timedelta
from core.db_manager import mongo_manager
from core.text_cleaner import NewsCleaner  # 引入上面的清洗器

logger = logging.getLogger("sync_news")
pro = ts.pro_api(os.getenv("TUSHARE_TOKEN", ""))


async def sync_daily_news():
    """
    每日新闻语料采集与清洗任务
    将高质量的新闻沉淀到 MongoDB 中，供舆情专员读取
    """
    logger.info("⏳ 开始执行 RAG 语料同步任务: 拉取并清洗全网金融新闻...")

    start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    end_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        df = pro.news(src='sina', start_date=start_date, end_date=end_date, limit=200)

        if df.empty:
            logger.info("💤 当前时段无最新新闻。")
            return

        valid_news_count = 0
        news_docs = []

        for _, row in df.iterrows():
            raw_content = row.get('content', '')
            raw_title = row.get('title', '')

            # 调用清洗器
            clean_content = NewsCleaner.process_news(raw_content, min_length=50)

            if clean_content:
                news_docs.append({
                    "datetime": row['datetime'],
                    "title": raw_title,
                    "content": clean_content,
                    "channels": row.get('channels', '')
                })
                valid_news_count += 1

        # 批量写入 MongoDB
        if news_docs:
            collection = mongo_manager.db["stock_news"]
            await collection.create_index("datetime", unique=True)

            for doc in news_docs:
                try:
                    await collection.update_one(
                        {"datetime": doc["datetime"]},
                        {"$set": doc},
                        upsert=True
                    )
                except Exception:
                    pass

        logger.info(f"✅ RAG 语料同步完成！共抓取 {len(df)} 条，清洗后沉淀高质量语料 {valid_news_count} 条。")

    except Exception as e:
        logger.error(f"❌ RAG 新闻语料同步失败: {e}")