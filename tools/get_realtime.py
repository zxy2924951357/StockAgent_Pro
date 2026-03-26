import asyncio
import math
import os
import random
import logging
from typing import Optional

import httpx
from langchain_core.tools import tool

logger = logging.getLogger("realtime_tools")


def _safe_float(val: object, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        s = str(val).strip()
        if s in ["", "-", "NaN", "nan", "None", "NaT"]:
            return default
        f = float(s)
        if math.isnan(f):
            return default
        return f
    except Exception:
        return default


def _get_em_secid(ts_code: str) -> str:
    # ts_code: "600098.SH" / "000001.SZ"
    code = ts_code[:6]
    if code.startswith(("6", "9", "5")):
        return f"1.{code}"
    return f"0.{code}"


@tool
async def query_realtime_price(ts_code: str) -> str:
    """
    查询单只股票的东财实时最新价/涨跌幅/成交额/成交量（尽力而为）。
    入参: ts_code, 例如 "600098.SH" / "000001.SZ" 或纯数字 "600098"。
    """
    if not ts_code:
        return "未提供股票代码。"

    # 允许传 "600098" 这种纯数字
    if "." not in ts_code:
        ts_code = f"{ts_code}.SH"  # 默认按上交所类处理，失败则返回空

    secid = _get_em_secid(ts_code)

    # 尽量复刻 market_api 的抓取风格，减少代理相关拦截
    for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
        os.environ.pop(k, None)

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]

    url = (
        "http://push2.eastmoney.com/api/qt/ulist.np/get"
        f"?secids={secid}"
        "&fields=f12,f14,f2,f3,f5,f8"
        "&fltt=2"
    )

    # 加一个轻微抖动与重试，提升成功率
    retries = 2
    last_err: Optional[str] = None
    for attempt in range(retries + 1):
        try:
            transport = httpx.AsyncHTTPTransport(retries=0)
            headers = {
                "User-Agent": random.choice(user_agents),
                "Accept": "*/*",
                "Referer": "http://quote.eastmoney.com/",
                "Connection": "keep-alive",
            }
            async with httpx.AsyncClient(
                verify=False,
                trust_env=False,
                headers=headers,
                http2=False,
                transport=transport,
                timeout=4.5,
            ) as client:
                res = await client.get(url)
                res.raise_for_status()
                data = res.json()

            items = data.get("data", {}).get("diff", [])
            if not items:
                return f"未获取到 {ts_code} 的实时行情数据。"

            item = items[0]
            price = _safe_float(item.get("f2"))
            change_pct = _safe_float(item.get("f3"))
            volume = _safe_float(item.get("f5"))
            turnover = _safe_float(item.get("f8"))
            name = item.get("f14", "").strip()

            # volume/f8 在东财接口里单位分别需要换算，这里只做基础输出
            volume_str = f"{volume:.0f}"
            turnover_str = f"{turnover:.0f}"

            display_name = name if name else ts_code
            sign = "+" if change_pct >= 0 else ""

            return (
                f"【实时行情】{display_name}({ts_code}) 最新价: {price:.2f} 元，"
                f"涨跌幅: {sign}{change_pct:.2f}% ，成交量: {volume_str} ，成交额: {turnover_str}。"
            )
        except Exception as e:
            last_err = str(e)
            # 失败退避
            await asyncio.sleep(0.35 + random.random() * 0.6)

    logger.error(f"query_realtime_price failed: {last_err}")
    return f"实时行情获取失败（{last_err}）。"

