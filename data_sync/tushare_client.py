# data_sync/tushare_client.py
import tushare as ts
import pandas as pd
from core.config import config
import logging

logger = logging.getLogger("tushare_client")

# 初始化 Tushare 接口
ts.set_token(config.TUSHARE_TOKEN)
pro = ts.pro_api()


def get_stock_basic() -> list[dict]:
    """获取所有上市股票的基本信息"""
    logger.info("开始从 Tushare 获取股票基础信息...")
    try:
        # 获取当前上市的股票数据 (L = 上市状态)
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')

        # 将 Pandas DataFrame 转换为字典列表，方便存入 MongoDB
        # records 模式会将每一行转为一个字典
        data_list = df.to_dict(orient='records')
        logger.info(f"成功获取到 {len(data_list)} 只股票数据")
        return data_list
    except Exception as e:
        logger.error(f"获取 Tushare 数据失败: {e}")
        return []