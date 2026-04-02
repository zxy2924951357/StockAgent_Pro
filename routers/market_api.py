import asyncio
import time
import math
import os
import httpx
import traceback
import random
import jwt
from typing import List
from fastapi import APIRouter, Query, Depends, Header, HTTPException
from pydantic import BaseModel
from core.db_manager import mongo_manager
from core.security import normalize_ts_code, sanitize_mongo_document, sanitize_stock_name, sanitize_text
from core.ui_translation import translate_texts_to_english
from core.stock_search import (
    build_stock_search_query,
    ensure_stock_search_fields,
    score_stock_match,
)


class WatchlistItem(BaseModel):
    ts_code: str
    stock_name: str


router = APIRouter(prefix="/api/market", tags=["market"])

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
            print(f"[network retry] attempt {attempt + 1}, wait {wait_time:.2f}s")
            await asyncio.sleep(wait_time)


_HOTSPOT_CACHE = {"data": None, "last_time": 0}
_TREND_CACHE = {}
_INDICES_CACHE = {"data": [], "last_time": 0}

HOTSPOT_TTL = 300
TREND_TTL = 30


def safe_float(val):
    try:
        if val is None:
            return 0.0
        s_val = str(val).strip()
        if s_val in ["", "-", "NaN", "nan", "None", "NaT"]:
            return 0.0
        f_val = float(s_val)
        if math.isnan(f_val):
            return 0.0
        return f_val
    except Exception:
        return 0.0


async def attach_name_en(items, field_name: str, domain: str):
    names_en = await translate_texts_to_english([item.get(field_name, "") for item in items], domain=domain)
    for item, value_en in zip(items, names_en):
        item[f"{field_name}_en"] = value_en
    return items


def get_em_secid(ts_code: str) -> str:
    ts_code_upper = ts_code.upper()
    if ts_code_upper.endswith(".SH"):
        return f"1.{ts_code[:6]}"
    if ts_code_upper.endswith(".SZ") or ts_code_upper.endswith(".BJ"):
        return f"0.{ts_code[:6]}"

    code = ts_code[:6]
    if code.startswith(('6', '9', '5')):
        return f"1.{code}"
    return f"0.{code}"


@router.get("/search")
async def search_stock(keyword: str = Query(...)):
    keyword = sanitize_text(keyword, field_name="搜索关键词", max_length=40)
    if not keyword:
        return {"code": 200, "data": []}
    collection = mongo_manager.db["stock_basic"]
    await ensure_stock_search_fields(collection)
    cursor = collection.find(
        build_stock_search_query(keyword),
        {"_id": 0, "ts_code": 1, "symbol": 1, "name": 1, "name_pinyin": 1, "name_initials": 1}
    ).limit(30)
    stocks = await cursor.to_list(length=30)
    ranked = sorted(stocks, key=lambda item: score_stock_match(item, keyword), reverse=True)[:8]
    translated_names = await translate_texts_to_english([item.get("name", "") for item in ranked], domain="stock_name")
    for item, name_en in zip(ranked, translated_names):
        item["name_en"] = name_en
    return {"code": 200, "data": ranked}


@router.post("/realtime")
async def get_realtime_prices(ts_codes: List[str]):
    normalized_codes = []
    for code in ts_codes[:80]:
        try:
            normalized_codes.append(normalize_ts_code(code))
        except HTTPException:
            continue
    if not normalized_codes:
        return {"code": 200, "data": []}
    secids = [get_em_secid(code) for code in normalized_codes]

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
    except Exception:
        return {"code": 200, "data": []}


@router.get("/trend")
async def get_stock_trend(ts_code: str = Query(...)):
    ts_code = normalize_ts_code(ts_code)
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
    limit = min(max(int(limit), 1), 50)
    global _HOTSPOT_CACHE
    now = time.time()
    if _HOTSPOT_CACHE["data"] and (now - _HOTSPOT_CACHE["last_time"]) < HOTSPOT_TTL:
        return {"code": 200, "data": await attach_name_en(await attach_name_en(_HOTSPOT_CACHE["data"], "sector_name", "sector_name"), "top_stock_name", "stock_name")}

    url = f"http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:2+f:!50&fields=f12,f14,f3,f128,f136"

    def get_fallback_data():
        return [
            {"sector_name": "人工智能(缓存)", "change_pct": 2.45, "top_stock_name": "科大讯飞", "top_stock_change": 5.23},
            {"sector_name": "光通信(缓存)", "change_pct": 1.88, "top_stock_name": "光迅科技", "top_stock_change": 3.45},
            {"sector_name": "半导体(缓存)", "change_pct": -0.56, "top_stock_name": "中芯国际", "top_stock_change": 1.22}
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
        await attach_name_en(result, "sector_name", "sector_name")
        await attach_name_en(result, "top_stock_name", "stock_name")

        _HOTSPOT_CACHE["data"] = result
        _HOTSPOT_CACHE["last_time"] = now
        return {"code": 200, "data": result}
    except Exception:
        if _HOTSPOT_CACHE["data"]:
            return {"code": 200, "data": await attach_name_en(await attach_name_en(_HOTSPOT_CACHE["data"], "sector_name", "sector_name"), "top_stock_name", "stock_name")}
        fallback_data = get_fallback_data()
        await attach_name_en(fallback_data, "sector_name", "sector_name")
        await attach_name_en(fallback_data, "top_stock_name", "stock_name")
        return {"code": 200, "data": fallback_data}


@router.get("/indices")
async def get_market_indices():
    global _INDICES_CACHE
    now = time.time()
    if _INDICES_CACHE["data"] and (now - _INDICES_CACHE["last_time"]) < 10:
        return {"code": 200, "data": await attach_name_en(_INDICES_CACHE["data"], "name", "index_name")}
    url = "http://push2.eastmoney.com/api/qt/ulist.np/get?secids=1.000001,0.399001,0.399006&fields=f14,f2,f3&fltt=2"
    try:
        data = await fetch_json_with_retry(url, timeout=4.0)
        items = data.get("data", {}).get("diff", [])
        if items:
            result = [
                {"name": i.get("f14", ""), "price": safe_float(i.get("f2")), "change_pct": safe_float(i.get("f3"))}
                for i in items
            ]
            await attach_name_en(result, "name", "index_name")
            _INDICES_CACHE["data"] = result
            _INDICES_CACHE["last_time"] = now
            return {"code": 200, "data": result}
    except Exception:
        pass
    return {"code": 200, "data": await attach_name_en(_INDICES_CACHE["data"], "name", "index_name")}


@router.post("/watchlist/add")
async def add_watchlist(item: WatchlistItem, current_user: str = Depends(get_current_user)):
    collection = mongo_manager.db["user_watchlist"]
    basic_coll = mongo_manager.db["stock_basic"]
    raw_input = normalize_ts_code(item.ts_code)
    await ensure_stock_search_fields(basic_coll)
    stock_info = await basic_coll.find_one({"ts_code": raw_input})
    if not stock_info:
        stock_info = await basic_coll.find_one({"symbol": raw_input[:6]})
    if not stock_info:
        stock_info = await basic_coll.find_one(build_stock_search_query(raw_input))
    if not stock_info:
        return {"code": 404, "msg": "未找到匹配的股票"}
    await collection.update_one(
        {"user_id": current_user, "ts_code": stock_info["ts_code"]},
        {"$set": sanitize_mongo_document({
            "user_id": current_user,
            "ts_code": stock_info["ts_code"],
            "stock_name": sanitize_stock_name(stock_info["name"]),
            "updated_at": time.time()
        })},
        upsert=True
    )
    return {"code": 200, "msg": "添加成功"}


@router.get("/watchlist/list")
async def get_watchlist(current_user: str = Depends(get_current_user)):
    data = await mongo_manager.db["user_watchlist"].find(
        {"user_id": current_user},
        {"_id": 0, "user_id": 0, "updated_at": 0}
    ).to_list(length=100)
    translated_names = await translate_texts_to_english([item.get("stock_name", "") for item in data], domain="stock_name")
    for item, stock_name_en in zip(data, translated_names):
        item["stock_name_en"] = stock_name_en
    return {"code": 200, "data": data}


@router.delete("/watchlist/remove")
async def remove_watchlist(ts_code: str = Query(...), current_user: str = Depends(get_current_user)):
    await mongo_manager.db["user_watchlist"].delete_one({"user_id": current_user, "ts_code": normalize_ts_code(ts_code)})
    return {"code": 200, "msg": "删除成功"}


@router.get("/kline")
async def get_stock_kline(ts_code: str = Query(...), limit: int = Query(60)):
    ts_code = normalize_ts_code(ts_code)
    limit = min(max(int(limit), 20), 240)
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
