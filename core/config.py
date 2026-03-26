# core/config.py
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

class Config:
    TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "stock_agent_lite")

config = Config()