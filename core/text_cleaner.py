# core/text_cleaner.py
import re
import logging

logger = logging.getLogger("text_cleaner")


class NewsCleaner:
    """
    从原版重型引擎中提取的 RAG 语料清洗器
    核心作用：过滤噪音，保证存入 MongoDB/向量库的文本绝对纯净
    """

    @staticmethod
    def clean_html(text: str) -> str:
        """去除 HTML 标签"""
        cleanr = re.compile('<.*?>')
        return re.sub(cleanr, '', text)

    @staticmethod
    def remove_urls_and_emails(text: str) -> str:
        """去除链接和邮箱"""
        text = re.sub(r'http\S+', '', text)
        text = re.sub(r'\S+@\S+', '', text)
        return text

    @staticmethod
    def remove_special_chars(text: str) -> str:
        """统一标点，去除影响 RAG 嵌入的奇怪不可见字符"""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\(免责声明：.*?\)', '', text)
        return text.strip()

    @classmethod
    def process_news(cls, text: str, min_length: int = 20) -> str:
        """全量清洗流水线"""
        if not isinstance(text, str) or not text:
            return ""

        text = cls.clean_html(text)
        text = cls.remove_urls_and_emails(text)
        text = cls.remove_special_chars(text)

        if len(text) < min_length:
            return ""

        return text