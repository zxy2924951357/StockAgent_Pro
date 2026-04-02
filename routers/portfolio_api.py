from typing import Optional
import datetime
import jwt
import os

from fastapi import APIRouter, Depends, Header, Query, HTTPException
from pydantic import BaseModel

from core.db_manager import mongo_manager
from core.security import normalize_ts_code, sanitize_mongo_document, sanitize_stock_name

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

SECRET_KEY = os.getenv("JWT_SECRET", "easyquant-super-secret-key-2026")
ALGORITHM = "HS256"


async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="登录信息无效")
        return username
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="登录信息无效")


class TradeAction(BaseModel):
    ts_code: str
    stock_name: str
    buy_price: float
    volume: int


class SellAction(BaseModel):
    ts_code: str
    sell_price: float = 0.0
    volume: int


@router.post("/buy")
async def buy_stock(trade: TradeAction, current_user: str = Depends(get_current_user)):
    ts_code = normalize_ts_code(trade.ts_code)
    stock_name = sanitize_stock_name(trade.stock_name)
    if trade.volume <= 0 or trade.buy_price <= 0:
        return {"code": 400, "msg": "价格和数量必须大于 0"}

    collection = mongo_manager.db["user_portfolio"]
    query = {"user_id": current_user, "ts_code": ts_code}
    existing = await collection.find_one(query)

    if existing:
        old_vol = existing["volume"]
        old_price = existing["avg_price"]
        new_vol = old_vol + trade.volume
        new_avg_price = (old_vol * old_price + trade.volume * trade.buy_price) / new_vol

        await collection.update_one(
            query,
            {"$set": sanitize_mongo_document({
                "stock_name": stock_name,
                "volume": new_vol,
                "avg_price": round(new_avg_price, 3),
                "updated_at": datetime.datetime.now()
            })}
        )
        return {"code": 200, "msg": f"加仓成功，最新摊薄成本 {new_avg_price:.2f}"}

    doc = sanitize_mongo_document({
        "user_id": current_user,
        "ts_code": ts_code,
        "stock_name": stock_name,
        "avg_price": trade.buy_price,
        "volume": trade.volume,
        "created_at": datetime.datetime.now(),
        "updated_at": datetime.datetime.now()
    })
    await collection.insert_one(doc)
    return {"code": 200, "msg": "建仓成功"}


@router.post("/sell")
async def sell_stock(
    action: Optional[SellAction] = None,
    ts_code: Optional[str] = Query(None),
    volume: Optional[int] = Query(None),
    current_user: str = Depends(get_current_user)
):
    raw_code = action.ts_code if action else ts_code or ""
    resolved_code = normalize_ts_code(raw_code)
    resolved_volume = action.volume if action else volume

    collection = mongo_manager.db["user_portfolio"]
    query = {"user_id": current_user, "ts_code": resolved_code}
    existing = await collection.find_one(query)

    if not existing:
        return {"code": 404, "msg": "未找到该标的持仓"}

    current_vol = existing.get("volume", 0)
    resolved_volume = current_vol if not resolved_volume or resolved_volume <= 0 else resolved_volume

    if resolved_volume >= current_vol:
        result = await collection.delete_one(query)
        if result.deleted_count > 0:
            return {"code": 200, "msg": "已全部清仓"}
        return {"code": 500, "msg": "清仓删除失败"}

    remain_vol = current_vol - resolved_volume
    await collection.update_one(
        query,
        {"$set": sanitize_mongo_document({
            "volume": remain_vol,
            "updated_at": datetime.datetime.now()
        })}
    )
    return {"code": 200, "msg": f"减仓成功，剩余 {remain_vol} 股"}


@router.get("/list")
async def get_portfolio(current_user: str = Depends(get_current_user)):
    cursor = mongo_manager.db["user_portfolio"].find(
        {"user_id": current_user},
        {"_id": 0, "user_id": 0}
    ).sort("updated_at", -1)
    portfolio = await cursor.to_list(length=100)
    return {"code": 200, "data": portfolio}
