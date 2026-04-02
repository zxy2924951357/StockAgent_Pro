from pydantic import BaseModel, Field
from typing import List, Optional
import datetime

# --- 模块一：基本信息 ---
class UserBasicInfo(BaseModel):
    username: str = Field(..., description="用户名")
    avatar_url: str = Field(default="https://api.dicebear.com/7.x/pixel-art/svg?seed=EasyQuant", description="默认极客风像素头像")
    created_at: datetime.datetime = Field(..., description="账号创建时间")

# --- 模块二：AI 专属投资画像 ---
class RadarData(BaseModel):
    category: str = Field(..., description="雷达图维度")
    value: int = Field(..., description="0-100的数值")

class AICopilotProfile(BaseModel):
    risk_preference: str = Field(..., description="激进 / 稳健 / 保守")
    trading_style: str = Field(..., description="交易风格标签")
    ai_notes: str = Field(..., description="AI 提取的性格备注")
    radar_chart: List[RadarData] = Field(..., description="雷达图数据源")

# --- 模块三：量化战绩速览 ---
class PerformanceStats(BaseModel):
    cumulative_pnl: float = Field(..., description="累计模拟收益 (%)")
    backtest_count: int = Field(..., description="历史回测次数")
    ai_report_count: int = Field(..., description="AI 诊断生成数")
    watchlist_count: int = Field(..., description="自选股追踪数")

# --- 模块四：系统与安全设置 ---
class QuantSettings(BaseModel):
    default_slippage: float = Field(default=0.0005, description="默认滑点")
    default_commission: float = Field(default=0.00025, description="默认佣金")
    theme: str = Field(default="dark", description="UI 主题")
    tushare_token: Optional[str] = Field(default=None, description="用户自带的 Tushare Token")

# --- 最终聚合输出 ---
class UserDashboardResponse(BaseModel):
    basic_info: UserBasicInfo
    ai_profile: AICopilotProfile
    stats: PerformanceStats
    settings: QuantSettings

# --- 接收请求体 ---
class CalibrateProfileRequest(BaseModel):
    new_risk_preference: str


class UpdateAvatarRequest(BaseModel):
    avatar_url: str


class UpdateThemeRequest(BaseModel):
    theme: str
