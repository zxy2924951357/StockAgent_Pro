# routers/auth_api.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import bcrypt
import jwt
import datetime
import os
from core.db_manager import mongo_manager

router = APIRouter(prefix="/api/auth", tags=["用户认证"])

# JWT 密钥（生产环境请放入 .env 文件中）
SECRET_KEY = os.getenv("JWT_SECRET", "easyquant-super-secret-key-2026")
ALGORITHM = "HS256"


class UserAuth(BaseModel):
    username: str
    password: str


# 使用原生 bcrypt 进行密码验证和加密
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: datetime.timedelta = datetime.timedelta(days=7)):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/register")
async def register(user: UserAuth):
    db = mongo_manager.db["users"]
    # 1. 检查用户是否已存在
    existing_user = await db.find_one({"username": user.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已被注册")

    # 2. 密码加密并入库
    hashed_password = get_password_hash(user.password)
    user_doc = {
        "username": user.username,
        "hashed_password": hashed_password,
        "created_at": datetime.datetime.utcnow()
    }
    await db.insert_one(user_doc)
    return {"code": 200, "msg": "注册成功，请前往登录页面！"}


@router.post("/login")
async def login(user: UserAuth):
    db = mongo_manager.db["users"]
    # 1. 验证用户存在与密码正确性
    db_user = await db.find_one({"username": user.username})
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 2. 签发 JWT Token
    access_token = create_access_token(data={"sub": user.username})
    return {
        "code": 200,
        "msg": "登录成功，正在接入终端...",
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username
    }