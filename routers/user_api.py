from fastapi import APIRouter, Depends, HTTPException, Header
import datetime
import jwt
import os

from core.db_manager import mongo_manager
from routers.market_api import fetch_json_with_retry, get_em_secid, safe_float
from schemas import UserDashboardResponse, CalibrateProfileRequest, UpdateAvatarRequest, UpdateThemeRequest

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


router = APIRouter(prefix="/api/user", tags=["Personal Center"])


async def get_portfolio_market_prices(portfolio_list):
    if not portfolio_list:
        return {}

    secids = [get_em_secid(item["ts_code"]) for item in portfolio_list if item.get("ts_code")]
    if not secids:
        return {}

    url = f"http://push2.eastmoney.com/api/qt/ulist.np/get?secids={','.join(secids)}&fields=f12,f2&fltt=2"
    try:
        data = await fetch_json_with_retry(url, timeout=4.0)
        diff = data.get("data", {}).get("diff", [])
        return {item.get("f12", ""): safe_float(item.get("f2")) for item in diff}
    except Exception:
        return {}


@router.get("/dashboard", response_model=UserDashboardResponse, summary="获取个人中心全景数据")
async def get_user_dashboard(current_user: str = Depends(get_current_user)):
    users_coll = mongo_manager.db["users"]
    profile_coll = mongo_manager.db["user_profile"]
    portfolio_coll = mongo_manager.db["user_portfolio"]
    watchlist_coll = mongo_manager.db["user_watchlist"]
    diagnostics_coll = mongo_manager.db["ai_diagnostics"]

    user_doc = await users_coll.find_one({"username": current_user}) or {}
    profile_doc = await profile_coll.find_one({"user_id": current_user}) or {}

    created_at = user_doc.get("created_at") or datetime.datetime.utcnow()
    avatar_url = profile_doc.get("avatar_url") or f"https://api.dicebear.com/7.x/pixel-art/svg?seed={current_user}"

    portfolio_list = await portfolio_coll.find({"user_id": current_user}, {"_id": 0}).to_list(length=200)
    watchlist_count = await watchlist_coll.count_documents({"user_id": current_user})
    ai_report_count = await diagnostics_coll.count_documents({"user_id": current_user})

    total_cost = 0.0
    total_market_value = 0.0
    latest_price_map = await get_portfolio_market_prices(portfolio_list)
    for item in portfolio_list:
        avg_price = float(item.get("avg_price", 0) or 0)
        volume = int(item.get("volume", 0) or 0)
        cost_amount = avg_price * volume
        total_cost += cost_amount
        latest_price = latest_price_map.get((item.get("ts_code") or "")[:6], avg_price)
        total_market_value += latest_price * volume

    cumulative_pnl = 0.0 if total_cost <= 0 else ((total_market_value - total_cost) / total_cost) * 100

    dashboard = {
        "basic_info": {
            "username": current_user,
            "avatar_url": avatar_url,
            "created_at": created_at,
        },
        "ai_profile": {
            "risk_preference": profile_doc.get("risk_preference", "稳健"),
            "trading_style": profile_doc.get("trading_style", "趋势跟踪 / 波段交易"),
            "ai_notes": profile_doc.get("notes", "画像持续更新中。"),
            "radar_chart": profile_doc.get("radar_chart", [
                {"category": "风险偏好", "value": 60},
                {"category": "短线敏捷", "value": 55},
                {"category": "中线耐心", "value": 70},
                {"category": "仓位管理", "value": 65},
                {"category": "纪律执行", "value": 58},
            ]),
        },
        "stats": {
            "cumulative_pnl": round(cumulative_pnl, 2),
            "backtest_count": 0,
            "ai_report_count": ai_report_count,
            "watchlist_count": watchlist_count,
        },
        "settings": {
            "default_slippage": 0.0005,
            "default_commission": 0.00025,
            "theme": profile_doc.get("theme", "night"),
            "tushare_token": None,
        },
    }
    return dashboard


@router.post("/profile/calibrate", summary="手动校准 AI 投资画像")
async def calibrate_ai_profile(request: CalibrateProfileRequest, current_user: str = Depends(get_current_user)):
    new_preference = request.new_risk_preference
    try:
        await mongo_manager.db["user_profile"].update_one(
            {"user_id": current_user},
            {"$set": {"risk_preference": new_preference}},
            upsert=True
        )
        return {
            "status": "success",
            "message": f"AI 已接收指令，你的风险偏好已更新为：{new_preference}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"画像校准失败: {str(e)}")


@router.post("/profile/avatar", summary="更新个人头像")
async def update_avatar(request: UpdateAvatarRequest, current_user: str = Depends(get_current_user)):
    avatar_url = (request.avatar_url or "").strip()
    if not avatar_url:
        raise HTTPException(status_code=400, detail="头像地址不能为空")

    await mongo_manager.db["user_profile"].update_one(
        {"user_id": current_user},
        {"$set": {"avatar_url": avatar_url, "updated_at": datetime.datetime.utcnow()}},
        upsert=True
    )
    return {"status": "success", "avatar_url": avatar_url}


@router.post("/settings/theme", summary="更新界面主题")
async def update_theme(request: UpdateThemeRequest, current_user: str = Depends(get_current_user)):
    theme = (request.theme or "").strip()
    if theme not in {"day", "night"}:
        raise HTTPException(status_code=400, detail="主题仅支持白天或黑夜")

    await mongo_manager.db["user_profile"].update_one(
        {"user_id": current_user},
        {"$set": {"theme": theme, "updated_at": datetime.datetime.utcnow()}},
        upsert=True
    )
    return {"status": "success", "theme": theme}
