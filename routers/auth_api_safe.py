import datetime
import os

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.db_manager import mongo_manager
from core.security import sanitize_mongo_document, validate_password, validate_username

router = APIRouter(prefix="/api/auth", tags=["用户认证"])

SECRET_KEY = os.getenv("JWT_SECRET", "easyquant-super-secret-key-2026")
ALGORITHM = "HS256"


class UserAuth(BaseModel):
    username: str
    password: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def create_access_token(data: dict, expires_delta: datetime.timedelta = datetime.timedelta(days=7)):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.datetime.utcnow() + expires_delta})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/register")
async def register(user: UserAuth):
    username = validate_username(user.username)
    password = validate_password(user.password)
    db = mongo_manager.db["users"]

    existing_user = await db.find_one({"username": username})
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已被注册")

    user_doc = sanitize_mongo_document({
        "username": username,
        "hashed_password": get_password_hash(password),
        "created_at": datetime.datetime.utcnow(),
    })
    await db.insert_one(user_doc)
    return {"code": 200, "msg": "注册成功，请前往登录页面"}


@router.post("/login")
async def login(user: UserAuth):
    username = validate_username(user.username)
    password = validate_password(user.password)
    db = mongo_manager.db["users"]

    db_user = await db.find_one({"username": username})
    if not db_user or not verify_password(password, db_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token = create_access_token(data={"sub": username})
    return {
        "code": 200,
        "msg": "登录成功，正在接入终端...",
        "access_token": access_token,
        "token_type": "bearer",
        "username": username,
    }
