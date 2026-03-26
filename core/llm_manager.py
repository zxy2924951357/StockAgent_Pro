# core/llm_manager.py
import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# 初始化全局大模型实例
llm = ChatOpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    model=os.getenv("LLM_MODEL"),
    temperature=0.3, # 温度设低一点，让金融分析更严谨客观
)