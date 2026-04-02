import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class UserBasicInfo(BaseModel):
    username: str = Field(..., description='用户名')
    avatar_url: str = Field(default='https://api.dicebear.com/7.x/pixel-art/svg?seed=EasyQuant', description='头像地址')
    created_at: datetime.datetime = Field(..., description='账号创建时间')


class RadarData(BaseModel):
    category: str = Field(..., description='雷达图维度')
    category_en: Optional[str] = Field(default=None, description='雷达图维度英文')
    value: int = Field(..., description='0-100 分值')


class AICopilotProfile(BaseModel):
    risk_preference: str = Field(..., description='风险偏好')
    risk_preference_en: Optional[str] = Field(default=None, description='风险偏好英文')
    trading_style: str = Field(..., description='交易风格')
    trading_style_en: Optional[str] = Field(default=None, description='交易风格英文')
    ai_notes: str = Field(..., description='AI 备注')
    ai_notes_en: Optional[str] = Field(default=None, description='AI 备注英文')
    radar_chart: List[RadarData] = Field(..., description='雷达图数据')


class PerformanceStats(BaseModel):
    cumulative_pnl: float = Field(..., description='累计盈亏百分比')
    backtest_count: int = Field(..., description='历史回测次数')
    ai_report_count: int = Field(..., description='AI 诊断生成数')
    watchlist_count: int = Field(..., description='自选数量')


class QuantSettings(BaseModel):
    default_slippage: float = Field(default=0.0005, description='默认滑点')
    default_commission: float = Field(default=0.00025, description='默认佣金')
    theme: str = Field(default='night', description='界面主题')
    language: str = Field(default='zh-CN', description='界面语言')
    tushare_token: Optional[str] = Field(default=None, description='用户自己的 Tushare Token')


class UserDashboardResponse(BaseModel):
    basic_info: UserBasicInfo
    ai_profile: AICopilotProfile
    stats: PerformanceStats
    settings: QuantSettings


class CalibrateProfileRequest(BaseModel):
    new_risk_preference: str


class UpdateAvatarRequest(BaseModel):
    avatar_url: str


class UpdateThemeRequest(BaseModel):
    theme: str


class UpdateLanguageRequest(BaseModel):
    language: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
