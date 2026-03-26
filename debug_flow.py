import os
import asyncio
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


import os
import asyncio
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# 1. 环境初始化 (🚨 这里的逻辑必须和 main.py 保持一致)
load_dotenv()

# 强制设置 API 密钥和地址
os.environ["OPENAI_API_KEY"] = os.getenv("LLM_API_KEY", "")
os.environ["OPENAI_API_BASE"] = os.getenv("LLM_BASE_URL", "")
CURRENT_MODEL = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")

print(f"⚙️ 正在检查 API KEY: {os.environ.get('OPENAI_API_KEY')[:10]}******")
print(f"⚙️ 正在使用模型: {CURRENT_MODEL}")

# 启动模型
llm = ChatOpenAI(model=CURRENT_MODEL, temperature=0)



# 2. 模拟大堂经理的意图提取
class IntentExtraction(BaseModel):
    intent: Literal["report", "chat"] = Field(
        description="如果要求生成某只股票的'深度诊断'、'研报'，提取为 'report'；提问、查数据、看大盘、闲聊为 'chat'"
    )
    ts_code: str = Field(default="", description="标准代码，如002230.SZ，无则留空")
    stock_name: str = Field(default="", description="股票中文名称，无则留空")


judge_llm = llm.with_structured_output(IntentExtraction)


async def run_debug():
    print("\n" + "=" * 50)
    print("🕵️‍♂️ 开始执行【手打纯文本输入】全链路诊断测试...")
    print("=" * 50)

    user_query = "请帮我生成一份科大讯飞的深度诊断研报。"
    print(f"\n👉 模拟用户手打输入: '{user_query}'")

    # --- 关卡 1: 意图识别测试 ---
    print("\n[关卡 1] 大堂经理听音辨意测试...")
    try:
        intent_data = await judge_llm.ainvoke(f"分析此请求：{user_query}")
        print(f"✅ 提取出的意图: {intent_data.intent}")
        print(f"✅ 提取出的名称: '{intent_data.stock_name}'")
        print(f"✅ 提取出的代码: '{intent_data.ts_code}'")

        if intent_data.intent != "report":
            print("🚨 [破案了！] 大模型把你生成研报的指令，当成了普通闲聊(chat)！")
            return
        if not intent_data.stock_name and not intent_data.ts_code:
            print("🚨 [破案了！] 大模型没能从你的话里提取出'科大讯飞'这个名字！")
            return
    except Exception as e:
        print(f"🚨 [关卡 1 崩溃] {e}")
        return

    # --- 关卡 2: 数据库匹配测试 ---
    print("\n[关卡 2] MongoDB 股票名录匹配测试...")
    try:
        from core.db_manager import mongo_manager
        target_name = intent_data.stock_name
        target_code = intent_data.ts_code

        query_cond = []
        if target_name: query_cond.append({"name": {"$regex": target_name}})
        if target_code: query_cond.append({"ts_code": {"$regex": target_code}})

        stock_info = await mongo_manager.db["stock_basic"].find_one({"$or": query_cond})
        if not stock_info:
            print(f"🚨 [破案了！] 数据库里找不到名为 '{target_name}' 的股票，请检查本地名录是否完整！")
            return

        real_ts_code = stock_info["ts_code"]
        real_name = stock_info["name"]
        print(f"✅ 成功从数据库反查出正确标的: {real_name} ({real_ts_code})")
    except Exception as e:
        print(f"🚨 [关卡 2 崩溃] {e}")
        return

    # --- 关卡 3: 底层打工仔测试 ---
    print("\n[关卡 3] 底层基本面团队实战测试...")
    try:
        from agent.fundamental import fund_agent
        test_prompt = f"你现在必须使用你的专属工具，查询【{real_name}】(标准股票代码：{real_ts_code}) 的基本面和估值。请给出详细文字分析。"
        print(f"👉 强行发给大模型的指令: {test_prompt}")

        res = await fund_agent.ainvoke({"messages": [HumanMessage(content=test_prompt)]})
        content = res["messages"][-1].content
        print(f"\n✅ 基本面团队回复 (截取前150字):\n{content[:150]}...\n")

        if "数据不足" in content or len(content) < 50:
            print("🚨 [破案了！] 基本面团队拿不到数据或在偷懒！")
    except Exception as e:
        print(f"🚨 [关卡 3 崩溃] {e}")

    print("\n🎉 诊断脚本执行完毕！")


if __name__ == "__main__":
    asyncio.run(run_debug())