# routers/portfolio_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.db_manager import mongo_manager
import datetime

router = APIRouter(prefix="/api/portfolio", tags=["持仓模拟盘"])


class TradeAction(BaseModel):
    ts_code: str
    stock_name: str
    buy_price: float  # 建仓成本价
    volume: int  # 持仓数量 (股)


class SellAction(BaseModel):
    ts_code: str
    sell_price: float = 0.0  # 卖出价格（当前主要用于前端展示，未来可扩展结算真实盈亏流水）
    volume: int  # 卖出数量 (股)


@router.post("/buy")
async def buy_stock(trade: TradeAction):
    """模拟买入/加仓"""
    if trade.volume <= 0 or trade.buy_price <= 0:
        return {"code": 400, "msg": "价格和数量必须大于0"}

    collection = mongo_manager.db["user_portfolio"]

    # 查找是否已有持仓
    existing = await collection.find_one({"ts_code": trade.ts_code})

    if existing:
        # 如果已经有持仓，需要重新计算加仓后的“平均成本”
        old_vol = existing["volume"]
        old_price = existing["avg_price"]

        new_vol = old_vol + trade.volume
        # 摊薄成本计算公式：(旧数量*旧价格 + 新数量*新价格) / 总数量
        new_avg_price = (old_vol * old_price + trade.volume * trade.buy_price) / new_vol

        await collection.update_one(
            {"ts_code": trade.ts_code},
            {"$set": {
                "volume": new_vol,
                "avg_price": round(new_avg_price, 3),
                "updated_at": datetime.datetime.now()
            }}
        )
        return {"code": 200, "msg": f"加仓成功，最新摊薄成本: {new_avg_price:.2f}"}
    else:
        # 首次建仓
        doc = {
            "ts_code": trade.ts_code,
            "stock_name": trade.stock_name,
            "avg_price": trade.buy_price,
            "volume": trade.volume,
            "created_at": datetime.datetime.now(),
            "updated_at": datetime.datetime.now()
        }
        await collection.insert_one(doc)
        return {"code": 200, "msg": "建仓成功"}


@router.post("/sell")
async def sell_stock(action: SellAction):
    """模拟减仓/清仓"""
    if action.volume <= 0:
        return {"code": 400, "msg": "卖出数量必须大于0"}

    collection = mongo_manager.db["user_portfolio"]

    # 1. 查出现有持仓
    existing = await collection.find_one({"ts_code": action.ts_code})

    if not existing:
        return {"code": 404, "msg": "未找到该标的持仓"}

    current_vol = existing.get("volume", 0)

    # 2. 判断是部分减仓还是彻底清仓
    if action.volume >= current_vol:
        # 卖出数量 >= 当前持仓，执行全部清仓
        result = await collection.delete_one({"ts_code": action.ts_code})
        if result.deleted_count > 0:
            return {"code": 200, "msg": "已全部清仓"}
        return {"code": 500, "msg": "清仓删除失败"}
    else:
        # 部分卖出 -> 扣减数量，买入均价保持不变
        remain_vol = current_vol - action.volume
        await collection.update_one(
            {"ts_code": action.ts_code},
            {"$set": {
                "volume": remain_vol,
                "updated_at": datetime.datetime.now()
            }}
        )
        return {"code": 200, "msg": f"减仓成功，剩余 {remain_vol} 股"}


@router.get("/list")
async def get_portfolio():
    """获取所有持仓列表"""
    cursor = mongo_manager.db["user_portfolio"].find({}, {"_id": 0}).sort("updated_at", -1)
    portfolio = await cursor.to_list(length=100)
    return {"code": 200, "data": portfolio}