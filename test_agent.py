# test_agent.py
import asyncio
from agent.graph import stock_agent_app


async def test_full_agent():
    print("\n🚀 启动 StockAgent 投研团队 🚀\n" + "=" * 40)

    # 初始化文件袋 (给好初始状态)
    initial_state = {
        "ts_code": "600519.SH",
        "stock_name": "贵州茅台",
        "fundamental_res": "",
        "technical_res": "",
        "sentiment_res": "",
        "final_report": ""
    }

    # 运行图 (invoke 内部会自动处理异步)
    final_state = await stock_agent_app.ainvoke(initial_state)

    print("\n" + "=" * 15 + " 最终研报出炉 " + "=" * 15)
    print(final_state.get("final_report", "分析失败，未生成报告"))


if __name__ == "__main__":
    # 这一句是程序执行的真正入口
    asyncio.run(test_full_agent())