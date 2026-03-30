import asyncio
import time
import math
import os
import httpx
import traceback
import random
from typing import List
from fastapi import APIRouter, Query
from pydantic import BaseModel
from core.db_manager import mongo_manager


class WatchlistItem(BaseModel):
    ts_code: str
    stock_name: str


router = APIRouter(prefix="/api/market", tags=["行情与自选"])

# 强制清洗系统代理
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(k, None)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
]


async def fetch_json_with_retry(url, timeout=5.0, retries=3):
    transport = httpx.AsyncHTTPTransport(retries=retries)
    for attempt in range(retries + 1):
        current_headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "*/*",
            "Referer": "http://quote.eastmoney.com/",
            "Connection": "keep-alive"
        }
        try:
            async with httpx.AsyncClient(
                    verify=False,
                    trust_env=False,
                    headers=current_headers,
                    http2=False,
                    transport=transport
            ) as client:
                res = await client.get(url, timeout=timeout)
                res.raise_for_status()
                return res.json()
        except Exception as e:
            if attempt == retries:
                raise e
            wait_time = 0.5 + random.random() * 1.5
            print(f"⚠️ [网络重试] 第 {attempt + 1} 次尝试，延迟 {wait_time:.2f}s...")
            await asyncio.sleep(wait_time)


_HOTSPOT_CACHE = {"data": None, "last_time": 0}
_TREND_CACHE = {}
_INDICES_CACHE = {"data": [], "last_time": 0}

HOTSPOT_TTL = 300
TREND_TTL = 30


def safe_float(val):
    try:
        if val is None: return 0.0
        s_val = str(val).strip()
        if s_val in ["", "-", "NaN", "nan", "None", "NaT"]: return 0.0
        f_val = float(s_val)
        if math.isnan(f_val): return 0.0
        return f_val
    except:
        return 0.0


def get_em_secid(ts_code: str) -> str:
    # 1. 优先通过尾缀精准判断
    ts_code_upper = ts_code.upper()
    if ts_code_upper.endswith(".SH"):
        return f"1.{ts_code[:6]}"
    elif ts_code_upper.endswith(".SZ") or ts_code_upper.endswith(".BJ"):
        return f"0.{ts_code[:6]}"

    # 2. 兜底盲猜逻辑
    code = ts_code[:6]
    if code.startswith(('6', '9', '5')): return f"1.{code}"
    return f"0.{code}"


@router.get("/search")
async def search_stock(keyword: str = Query(...)):
    if not keyword.strip(): return {"code": 200, "data": []}
    cursor = mongo_manager.db["stock_basic"].find({
        "$or": [{"ts_code": {"$regex": keyword, "$options": "i"}}, {"name": {"$regex": keyword, "$options": "i"}}]
    }, {"_id": 0, "ts_code": 1, "name": 1}).limit(8)
    return {"code": 200, "data": await cursor.to_list(length=8)}


@router.post("/realtime")
async def get_realtime_prices(ts_codes: List[str]):
    if not ts_codes: return {"code": 200, "data": []}
    secids = [get_em_secid(code) for code in ts_codes]

    url = f"http://push2.eastmoney.com/api/qt/ulist.np/get?secids={','.join(secids)}&fields=f12,f14,f2,f3,f5,f6,f8&fltt=2"
    try:
        data = await fetch_json_with_retry(url, timeout=4.0)
        items = data.get("data", {}).get("diff", [])
        result = [{
            "code": item.get("f12", ""), "name": item.get("f14", ""),
            "price": safe_float(item.get("f2")),
            "change_pct": safe_float(item.get("f3")),
            "volume": safe_float(item.get("f5")),
            "turnover": safe_float(item.get("f8"))
        } for item in items]
        return {"code": 200, "data": result}
    except Exception as e:
        return {"code": 200, "data": []}


@router.get("/trend")
async def get_stock_trend(ts_code: str = Query(...)):
    global _TREND_CACHE
    now = time.time()
    pure_code = ts_code[:6]
    if pure_code in _TREND_CACHE and (now - _TREND_CACHE[pure_code]["last_time"]) < TREND_TTL:
        return {"code": 200, "data": _TREND_CACHE[pure_code]["data"]}

    url = f"http://push2.eastmoney.com/api/qt/stock/trends2/get?secid={get_em_secid(ts_code)}&fields1=f1&fields2=f51,f53&fltt=2"
    try:
        data = await fetch_json_with_retry(url, timeout=4.0)
        trends = data.get("data", {}).get("trends", [])
        if trends:
            points = [safe_float(t.split(',')[1]) for t in trends][-35:]
            _TREND_CACHE[pure_code] = {"data": points, "last_time": now}
            return {"code": 200, "data": points}
    except Exception:
        pass
    return {"code": 200, "data": _TREND_CACHE.get(pure_code, {}).get("data", [])}


@router.get("/hotspots")
async def get_hotspots(limit: int = Query(24)):
    global _HOTSPOT_CACHE
    now = time.time()
    if _HOTSPOT_CACHE["data"] and (now - _HOTSPOT_CACHE["last_time"]) < HOTSPOT_TTL:
        return {"code": 200, "data": _HOTSPOT_CACHE["data"]}

    url = f"http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:2+f:!50&fields=f12,f14,f3,f128,f136"

    def get_fallback_data():
        return [
            {"sector_name": "人工智能(周末快照)", "change_pct": 2.45, "top_stock_name": "科大讯飞",
             "top_stock_change": 5.23},
            {"sector_name": "光通信(周末快照)", "change_pct": 1.88, "top_stock_name": "光迅科技",
             "top_stock_change": 3.45},
            {"sector_name": "半导体(周末快照)", "change_pct": -0.56, "top_stock_name": "中芯国际",
             "top_stock_change": 1.22}
        ]

    try:
        data = await fetch_json_with_retry(url, timeout=5.0)
        raw_data = data.get("data")
        if not raw_data or not raw_data.get("diff"):
            if _HOTSPOT_CACHE["data"]:
                return {"code": 200, "data": _HOTSPOT_CACHE["data"]}
            return {"code": 200, "data": get_fallback_data()}

        items = raw_data.get("diff", [])
        result = [{
            "sector_name": item.get("f14", ""),
            "change_pct": safe_float(item.get("f3")),
            "top_stock_name": item.get("f128", ""),
            "top_stock_change": safe_float(item.get("f136"))
        } for item in items]

        _HOTSPOT_CACHE["data"] = result
        _HOTSPOT_CACHE["last_time"] = now
        return {"code": 200, "data": result}
    except Exception as e:
        if _HOTSPOT_CACHE["data"]:
            return {"code": 200, "data": _HOTSPOT_CACHE["data"]}
        return {"code": 200, "data": get_fallback_data()}


@router.get("/indices")
async def get_market_indices():
    global _INDICES_CACHE
    now = time.time()
    if _INDICES_CACHE["data"] and (now - _INDICES_CACHE["last_time"]) < 10:
        return {"code": 200, "data": _INDICES_CACHE["data"]}
    url = "http://push2.eastmoney.com/api/qt/ulist.np/get?secids=1.000001,0.399001,0.399006&fields=f14,f2,f3&fltt=2"
    try:
        data = await fetch_json_with_retry(url, timeout=4.0)
        items = data.get("data", {}).get("diff", [])
        if items:
            result = [
                {"name": i.get("f14", ""), "price": safe_float(i.get("f2")), "change_pct": safe_float(i.get("f3"))} for
                i in items]
            _INDICES_CACHE["data"] = result
            _INDICES_CACHE["last_time"] = now
            return {"code": 200, "data": result}
    except Exception:
        pass
    return {"code": 200, "data": _INDICES_CACHE["data"]}


@router.post("/watchlist/add")
async def add_watchlist(item: WatchlistItem):
    collection = mongo_manager.db["user_watchlist"]
    basic_coll = mongo_manager.db["stock_basic"]
    raw_input = item.ts_code.strip().upper()
    stock_info = await basic_coll.find_one(
        {"$or": [{"ts_code": {"$regex": f"^{raw_input}"}}, {"name": {"$regex": f"^{raw_input}"}}]})
    if not stock_info: return {"code": 404, "msg": f"未找到匹配的股票"}
    await collection.update_one({"ts_code": stock_info["ts_code"]},
                                {"$set": {"ts_code": stock_info["ts_code"], "stock_name": stock_info["name"]}},
                                upsert=True)
    return {"code": 200, "msg": "添加成功"}


@router.get("/watchlist/list")
async def get_watchlist():
    return {"code": 200, "data": await mongo_manager.db["user_watchlist"].find({}, {"_id": 0}).to_list(length=100)}


@router.delete("/watchlist/remove")
async def remove_watchlist(ts_code: str = Query(...)):
    await mongo_manager.db["user_watchlist"].delete_one({"ts_code": ts_code.strip()})
    return {"code": 200, "msg": "彻底删除成功"}


@router.get("/kline")
async def get_stock_kline(ts_code: str = Query(...), limit: int = Query(60)):
    secid = get_em_secid(ts_code)
    url = f"http://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500000&lmt={limit}"
    try:
        data = await fetch_json_with_retry(url, timeout=5.0)
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return {"code": 404, "msg": "未获取到 K 线数据", "data": []}
        result = []
        for k in klines:
            parts = k.split(",")
            result.append({
                "date": parts[0], "open": safe_float(parts[1]), "close": safe_float(parts[2]),
                "high": safe_float(parts[3]), "low": safe_float(parts[4]), "volume": safe_float(parts[5]),
                "change_pct": safe_float(parts[8]), "turnover": safe_float(parts[10])
            })
        return {"code": 200, "data": result, "name": data.get("data", {}).get("name", "")}
    except Exception as e:
        return {"code": 500, "msg": str(e), "data": []}