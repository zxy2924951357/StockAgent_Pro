# agent/chat_graph.py
import os
from typing import Annotated, TypedDict, Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver  # ✨ 新增：记忆存储器

# 导入四大独立专家，以及他们的人设词
from agent.fundamental import fund_agent, FUNDAMENTAL_PROMPT
from agent.technical import tech_agent, TECHNICAL_PROMPT
from agent.macro import macro_agent, MACRO_PROMPT
from agent.general import general_agent, GENERAL_PROMPT

load_dotenv()
CURRENT_MODEL = os.getenv("LLM_MODEL", "qwen3-vl-plus-2025-09-23")
llm = ChatOpenAI(model=CURRENT_MODEL, temperature=0)

class ChatState(TypedDict):
    messages: Annotated[list, add_messages]
    next_agent: str

class RouteDecision(BaseModel):
    next_agent: Literal["fundamental", "technical", "macro", "general"] = Field(
        description="""
        分析用户的意图，分配给最合适的专家：
        - fundamental: 问估值、PE/PB、基本面、市盈率、财报。
        - technical: 问均线、支撑位、放量缩量、近期走势、在底部吗；也包括问“现在股价/最新报价/当前价/实时行情”。
        - macro: 问大盘、指数、热点板块、资金炒什么、推荐股票、选股、帮我找好票、今天有什么大新闻、全网快讯聚合。 
        - general: 闲聊、打招呼、金融名词解释、公司主营业务介绍。
        """
    )
    # 🌟 上面我给 macro 加上了“推荐股票、选股、帮我找好票、今天有什么大新闻、全网快讯聚合”的引导词

router_llm = llm.with_structured_output(RouteDecision)

async def dispatcher_node(state: ChatState):
    user_query = state["messages"][-1].content
    print(f"🚦 [大堂经理] 正在听音辨意: '{user_query}'")
    decision = await router_llm.ainvoke(user_query)
    print(f"🎯 [大堂经理] 意图锁定 -> 已挂号给【{decision.next_agent.upper()}】专家")
    return {"next_agent": decision.next_agent}

# ==== 动态注入人设 ====
async def call_fundamental(state: ChatState):
    messages = [SystemMessage(content=FUNDAMENTAL_PROMPT)] + state["messages"]
    res = await fund_agent.ainvoke({"messages": messages})
    return {"messages": [res["messages"][-1]]}

async def call_technical(state: ChatState):
    messages = [SystemMessage(content=TECHNICAL_PROMPT)] + state["messages"]
    res = await tech_agent.ainvoke({"messages": messages})
    return {"messages": [res["messages"][-1]]}

async def call_macro(state: ChatState):
    messages = [SystemMessage(content=MACRO_PROMPT)] + state["messages"]
    res = await macro_agent.ainvoke({"messages": messages})
    return {"messages": [res["messages"][-1]]}

async def call_general(state: ChatState):
    messages = [SystemMessage(content=GENERAL_PROMPT)] + state["messages"]
    res = await general_agent.ainvoke({"messages": messages})
    return {"messages": [res["messages"][-1]]}

workflow = StateGraph(ChatState)

workflow.add_node("dispatcher", dispatcher_node)
workflow.add_node("fundamental", call_fundamental)
workflow.add_node("technical", call_technical)
workflow.add_node("macro", call_macro)
workflow.add_node("general", call_general)

workflow.add_edge(START, "dispatcher")
workflow.add_conditional_edges(
    "dispatcher",
    lambda x: x["next_agent"],
    {
        "fundamental": "fundamental",
        "technical": "technical",
        "macro": "macro",
        "general": "general"
    }
)

workflow.add_edge("fundamental", END)
workflow.add_edge("technical", END)
workflow.add_edge("macro", END)
workflow.add_edge("general", END)

# ✨ 实例化记忆存储器并注入到编译中
memory = MemorySaver()
chat_agent_app = workflow.compile(checkpointer=memory)