# routers/backtest_api.py
import pandas as pd
import numpy as np
from fastapi import APIRouter, Query
from routers.market_api import get_em_secid, fetch_json_with_retry

router = APIRouter(prefix="/api/backtest", tags=["策略回测沙盒"])


@router.get("/run")
async def run_backtest(ts_code: str = Query(...), strategy: str = Query("ma_cross")):
    """
    极速向量化回测引擎 (多战法版)
    """
    secid = get_em_secid(ts_code)
    # 获取近 500 个交易日的日K线数据
    url = f"http://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500000&lmt=500"

    try:
        res = await fetch_json_with_retry(url)
        klines = res.get("data", {}).get("klines", [])

        if not klines or len(klines) < 60:
            return {"code": 400, "msg": "历史数据不足，无法回测", "data": None}

        # 数据清洗
        parsed = [{"date": k.split(",")[0], "close": float(k.split(",")[2])} for k in klines]
        df = pd.DataFrame(parsed)

        strategy_name_zh = "未知策略"

        # ==================================================
        # ⚔️ 战法 1：经典双均线交叉 (趋势跟随)
        # ==================================================
        if strategy == "ma_cross":
            strategy_name_zh = "双均线交叉策略 (MA5穿MA20)"
            df['MA5'] = df['close'].rolling(window=5).mean()
            df['MA20'] = df['close'].rolling(window=20).mean()
            df['signal'] = np.where(df['MA5'] > df['MA20'], 1, 0)
            df['position'] = df['signal'].shift(1).fillna(0)

        # ==================================================
        # ⚔️ 战法 2：MACD 动能顺势 (波段突破)
        # ==================================================
        elif strategy == "macd_trend":
            strategy_name_zh = "MACD波段跟随 (DIF金叉)"
            # 计算 MACD 指标
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            dif = exp1 - exp2
            dea = dif.ewm(span=9, adjust=False).mean()
            # DIF 站上 DEA 看多
            df['signal'] = np.where(dif > dea, 1, 0)
            df['position'] = df['signal'].shift(1).fillna(0)

        # ==================================================
        # ⚔️ 战法 3：RSI 超卖抄底反弹 (均值回复)
        # ==================================================
        elif strategy == "rsi_reversion":
            strategy_name_zh = "RSI超卖抄底反弹 (低吸高抛)"
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-9)  # 防止除以0
            df['RSI'] = 100 - (100 / (1 + rs))

            # RSI < 30 买入标记为 1，RSI > 60 卖出标记为 -1
            df['buy_sig'] = np.where(df['RSI'] < 30, 1, 0)
            df['sell_sig'] = np.where(df['RSI'] > 60, -1, 0)

            # 使用 pandas 特性实现状态机（持仓保持）
            df['action'] = df['buy_sig'] + df['sell_sig']
            df['signal'] = df['action'].replace(0, np.nan).ffill().replace(-1, 0).fillna(0)
            df['position'] = df['signal'].shift(1).fillna(0)

        else:
            return {"code": 400, "msg": "未知的战法"}

        # ==================================================
        # 核心收益计算
        # ==================================================
        df['daily_return'] = df['close'].pct_change().fillna(0)
        df['strategy_return'] = df['position'] * df['daily_return']

        df['stock_net'] = (1 + df['daily_return']).cumprod()
        df['strategy_net'] = (1 + df['strategy_return']).cumprod()

        # 计算 KPI
        total_strategy_return = df['strategy_net'].iloc[-1] - 1
        total_stock_return = df['stock_net'].iloc[-1] - 1

        win_days = len(df[df['strategy_return'] > 0])
        trade_days = len(df[df['position'] > 0])
        win_rate = (win_days / trade_days * 100) if trade_days > 0 else 0

        roll_max = df['strategy_net'].cummax()
        drawdown = df['strategy_net'] / roll_max - 1
        max_drawdown = drawdown.min() * 100

        df = df.fillna(0)

        return {
            "code": 200,
            "data": {
                "strategy_name": strategy_name_zh,  # 传回中文名称供前端展示
                "kpi": {
                    "strategy_return_pct": round(total_strategy_return * 100, 2),
                    "stock_return_pct": round(total_stock_return * 100, 2),
                    "win_rate": round(win_rate, 2),
                    "max_drawdown": round(max_drawdown, 2),
                    "trade_days": int(trade_days)
                },
                "chart": {
                    "dates": df['date'].tolist(),
                    "stock_net": df['stock_net'].round(4).tolist(),
                    "strategy_net": df['strategy_net'].round(4).tolist(),
                }
            }
        }

    except Exception as e:
        return {"code": 500, "msg": f"回测引擎崩溃: {str(e)}", "data": None}