# tools/get_report.py
import logging
import akshare as ak
import asyncio
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger("tool_rag")

# 1. 全局初始化 Embedding 模型，避免每次查询重复加载模型权重耗时
logger.info("⏳ 正在加载本地 BAAI/bge-small-zh-v1.5 嵌入模型...")
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-zh-v1.5")
logger.info("✅ 嵌入模型加载完毕！")


async def query_research_report(ts_code: str, query: str = "公司的核心业务、基本面与护城河", limit: int = 40,
                                top_k: int = 3) -> str:
    """
    动态内存 RAG：
    1. 用 AkShare 实时抓取最近 40 条资讯
    2. 在内存中瞬间构建临时 FAISS 向量库
    3. 根据 query 进行语义检索，返回最相关的 top_k 条精准情报
    """
    symbol = ts_code.split(".")[0]
    logger.info(f"🔍 动态 RAG 启动: 正在为 {ts_code} 构建临时知识库...")

    try:
        # 1. 广撒网：获取大量的近期资讯（不阻塞主线程）
        news_df = await asyncio.to_thread(ak.stock_news_em, symbol=symbol)

        if news_df is None or news_df.empty:
            logger.warning(f"⚠️ 未抓取到 {ts_code} 的近期资讯。")
            return "数据库中暂未收录该公司的近期研报或深度定性分析。"

        # 取前 limit 条数据用于构建临时知识库
        news_df = news_df.head(limit)

        # 2. 数据清洗与 Document 对象转换
        docs = []
        for index, row in news_df.iterrows():
            title = row.get("新闻标题", "无标题")
            content = str(row.get("新闻内容", "无内容"))

            # 过滤掉低于 30 个字的无意义快讯
            if len(content) < 30:
                continue

            # 拼接文本并打上 Metadata 标签
            doc_text = f"标题: {title}\n内容: {content}"
            metadata = {
                "source": row.get("文章来源", "券商/媒体"),
                "publish_time": row.get("发布时间", "未知时间")
            }
            docs.append(Document(page_content=doc_text, metadata=metadata))

        if not docs:
            return "抓取到的资讯内容过短，无法构建有效的语义检索库。"

        logger.info(f"🧠 正在将 {len(docs)} 篇长文本转化为向量并注入内存 FAISS...")

        # 3. 内存建库：由于文本量不大，这步在 CPU 上极快（约1-2秒）
        vector_store = await asyncio.to_thread(FAISS.from_documents, docs, embeddings)

        # 4. 精准检索：核心 RAG 步骤
        logger.info(f"🎯 正在针对问题 ['{query}'] 执行语义匹配...")
        retriever = vector_store.as_retriever(search_kwargs={"k": top_k})
        relevant_docs = await asyncio.to_thread(retriever.invoke, query)

        # 5. 拼装高质量上下文喂给大模型
        context = f"【关于“{query}”的精准检索结果】\n\n"
        for i, doc in enumerate(relevant_docs, 1):
            context += f"📄 检索片段 {i}\n"
            context += f"🕒 发布时间: {doc.metadata['publish_time']} | 🏢 来源: {doc.metadata['source']}\n"
            context += f"📝 内容: {doc.page_content}\n"
            context += "-" * 50 + "\n"

        logger.info(f"✅ 动态 RAG 检索完成！成功提取 {len(relevant_docs)} 篇高度相关的报告。")
        return context

    except Exception as e:
        logger.error(f"❌ 动态 RAG 检索彻底失败: {e}")
        return "暂无关于该公司的定性研报数据，请仅基于财务报表数字进行分析。"