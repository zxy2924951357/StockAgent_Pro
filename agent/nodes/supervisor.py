# agent/nodes/supervisor.py
import logging
import datetime
from agent.state import AgentState
from core.llm_manager import llm
from core.db_manager import mongo_manager
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("node_supervisor")

async def supervisor_node(state: AgentState):
    stock_name = state.get("stock_name", "未知标的")
    ts_code = state.get("ts_code", "")
    fina_res = state.get("fundamental_res", "")
    tech_res = state.get("technical_res", "")
    sent_res = state.get("sentiment_res", "")
    critique = state.get("critique", "")

    # 获取当前真实时间，注入给大模型
    current_date = datetime.datetime.now().strftime("%Y年%m月%d日")

    logger.info(f"==> 👨‍💼 统稿环节：正在以专家视角深度整合 {stock_name} 的素材...")

    # 模块二：动态注入客户画像（失败时静默降级，不中断主流程）
    profile_block = ""
    try:
        profile_doc = await mongo_manager.db["user_profile"].find_one({"user_id": "admin"}, {"_id": 0})
        if profile_doc:
            risk_pref = profile_doc.get("risk_preference", "未知")
            trading_style = profile_doc.get("trading_style", "")
            notes = profile_doc.get("notes", "")
            profile_block = (
                "\n【客户画像】\n"
                f"- 风险偏好: {risk_pref}\n"
                f"- 交易风格: {trading_style if trading_style else '未识别'}\n"
                f"- 画像备注: {notes if notes else '无'}\n"
            )
            logger.info(f"🧠 已注入客户画像: risk={risk_pref}, style={trading_style}")
    except Exception as e:
        logger.warning(f"⚠️ 读取客户画像失败(已忽略): {e}")

    # 🌟 重构的高阶系统提示词 (注入反幻觉绝对红线)
    sys_prompt = f"""你是一位拥有10年经验的A股资深行研分析师兼量化策略专家。今天是 {current_date}。
你的任务是将下属提供的异构数据（基本面、技术面、资金情绪面）进行【深度逻辑整合】，撰写一份专业、客观、逻辑自洽的深度诊断报告。

【🔴 核心铁律：反幻觉与数据真实性绝对红线】
1. 绝对禁止数据造假与推测：你【只能】基于下属提供的素材进行分析整合。如果素材中显示“未获取到数据”、“缺少最新财报”、“暂无资金流向”，你必须在研报中如实写明“因底层数据库未同步，缺乏相关客观数据支撑”，绝对不允许动用你的预训练知识库去“合理推测”、“推演”或编造任何财务/技术数据！
2. 逻辑自洽与冲突消除：如果技术面提示“多头排列/资金流入”，但舆情面提示“主力出逃/负面利空”，你必须指出这种【背离】，并给出合理的金融学解释。
3. 拒绝废话套话：必须从基本面素材中提取该公司的“核心技术壁垒”、“稀缺性”或“财务雷点”。严禁在没有真实数据支撑的情况下做财务排雷。

【🟡 格式红线：严苛的排版要求】
1. 必须使用标准的 Markdown 语法。禁止输出任何 JSON 格式。
2. 遇到【综合投资建议】的表格时，严禁压缩成单行！必须使用规范的 Markdown 跨行表格格式，包含表头和对齐分隔线。
✅ 正确表格示范：
| 投资类型 | 操作建议 | 核心关注点 |
| :--- | :--- | :--- |
| 长线投资者 | 逢低定投，等待财报验证 | 核心技术落地与订单转化 |
| 波段交易者 | 80元附近试探建仓，跌破止损 | 技术均线支撑与量价配合 |

【🟢 必须包含的报告结构】：
# {stock_name} ({ts_code}) 深度诊断报告
## 一、 基本面质地分析 (行业定位、核心壁垒、财务排雷预警)
## 二、 技术面走势研判 (均线系统、资金动向、多空博弈点评)
## 三、 风险警示 (提炼舆情与资金面的潜在共振风险)
## 四、 综合投资建议 (必须以规范的 Markdown 表格呈现)
请将【综合投资建议】与客户画像严格对齐：风险偏好保守时避免激进仓位建议；风险偏好激进时可给出更高波动策略但必须明确止损纪律。
{profile_block}
"""

    # 🌟 致命修复：删除了允许推测的指令，强硬要求“没有数据就如实说明”
    human_prompt = f"""
请【严格且仅基于】以下原始素材，为 {stock_name} ({ts_code}) 撰写最终研报。
如果素材中有缺失部分，请直接跳过该部分的深度分析或如实说明缺乏数据，绝不准自行推测！

[基本面素材]：
{fina_res}

[技术面素材]：
{tech_res}

[舆情素材]：
{sent_res}
"""

    if critique:
        logger.warning("⚠️ 统稿节点收到回测打回意见，触发针对性重写。")
        human_prompt += f"""

====================
【回测闸门打回意见】
{critique}

请针对上述回测警报，重点修订：技术面关键位、风控阈值、仓位建议与止损纪律，并避免空泛表述。
"""

    try:
        # 调用大模型生成统稿
        response = await llm.ainvoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=human_prompt)
        ])

        final_text = response.content.strip()

        logger.info(f"✅ 统稿完成，原始字数: {len(final_text)}")
        return {"final_report": final_text}

    except Exception as e:
        logger.error(f"❌ 统稿节点崩溃: {e}")
        return {"final_report": f"研报统稿失败，请检查模型连接。内容: {str(e)}"}