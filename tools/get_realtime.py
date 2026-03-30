import asyncio
import math
import os
import random
import logging
import re
from typing import Optional

import httpx
from langchain_core.tools import tool
from core.db_manager import mongo_manager

logger = logging.getLogger("realtime_tools")


def _safe_float(val: object, default: float = 0.0) -> float:
    try:
        if val is None: return default
        s = str(val).strip()
        if s in ["", "-", "NaN", "nan", "None", "NaT"]: return default
        f = float(s)
        if math.isnan(f): return default
        return f
    except Exception:
        return default


def _get_em_secid(ts_code: str) -> str:
    ts_code_upper = ts_code.upper()
    if ts_code_upper.endswith(".SH"):
        return f"1.{ts_code[:6]}"
    elif ts_code_upper.endswith(".SZ") or ts_code_upper.endswith(".BJ"):
        return f"0.{ts_code[:6]}"

    code = ts_code[:6]
    if code.startswith(("6", "9", "5")): return f"1.{code}"
    return f"0.{code}"


@tool
async def query_realtime_price(ts_code: str) -> str:
    """
    查询单只股票的东财实时最新价/涨跌幅/成交额/成交量/换手率。
    入参: ts_code, 可以是代码(如 "300109.SZ")，也可以是中文(如 "新开源")。
    """
    if not ts_code: return "【系统警告】未提供股票代码，严禁编造数据！"

    query_str = ts_code.strip()

    if re.search(r'[\u4e00-\u9fa5]', query_str):
        try:
            stock_info = await mongo_manager.db["stock_basic"].find_one({
                "name": {"$regex": query_str, "$options": "i"}
            })
            if stock_info:
                query_str = stock_info["ts_code"]
            else:
                return f"【系统警告】数据库查不到【{ts_code}】，请如实告诉用户无法获取，绝对禁止瞎编数据！"
        except Exception:
            pass

    # ⚠️ 修复致命BUG：智能判断后缀，不再无脑统一加 .SH
    if "." not in query_str:
        if query_str.startswith(("6", "9", "5")):
            query_str = f"{query_str}.SH"
        elif query_str.startswith(("8", "4", "3")):
            query_str = f"{query_str}.BJ" if query_str.startswith(("8", "4")) else f"{query_str}.SZ"
        else:
            query_str = f"{query_str}.SZ"

    secid = _get_em_secid(query_str)

    for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
        os.environ.pop(k, None)

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]

    url = f"http://push2.eastmoney.com/api/qt/ulist.np/get?secids={secid}&fields=f12,f14,f2,f3,f5,f6,f8&fltt=2"

    retries = 2
    for attempt in range(retries + 1):
        try:
            transport = httpx.AsyncHTTPTransport(retries=0)
            headers = {"User-Agent": random.choice(user_agents), "Accept": "*/*",
                       "Referer": "http://quote.eastmoney.com/", "Connection": "keep-alive"}
            async with httpx.AsyncClient(verify=False, trust_env=False, headers=headers, http2=False,
                                         transport=transport, timeout=4.5) as client:
                res = await client.get(url)
                res.raise_for_status()
                data = res.json()

            items = data.get("data", {}).get("diff", [])
            if not items:
                # 🌟 强力锁：如果东财没数据，直接在底层阻断幻觉！
                return f"【系统拦截】接口未返回 {query_str} 的数据。请原样回复用户：行情拉取为空，绝对禁止你自己捏造任何数字！"

            item = items[0]
            price = _safe_float(item.get("f2"))
            change_pct = _safe_float(item.get("f3"))
            volume = _safe_float(item.get("f5"))
            amount = _safe_float(item.get("f6"))
            turnover_rate = _safe_float(item.get("f8"))
            name = item.get("f14", "").strip()

            volume_str = f"{volume / 10000:.2f}万手" if volume > 0 else "0"
            amount_str = f"{amount / 100000000:.2f}亿元" if amount > 0 else "0"
            turnover_rate_str = f"{turnover_rate:.2f}%"
            sign = "+" if change_pct >= 0 else ""

            return (f"【实时行情】{name}({query_str[:6]}) 最新价: {price:.2f} 元，"
                    f"涨跌幅: {sign}{change_pct:.2f}% ，成交量: {volume_str} ，"
                    f"成交额: {amount_str} ，换手率: {turnover_rate_str}。")
        except Exception:
            await asyncio.sleep(0.35 + random.random() * 0.6)

    return "【系统拦截】实时行情网络超时。请告诉用户接口超时，绝对禁止捏造数据！"