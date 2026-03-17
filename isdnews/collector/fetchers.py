import asyncio
import aiohttp
import feedparser
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from email.utils import parsedate_to_datetime
import re
import html
import ssl
import certifi

from .utils import get_agentql_api_key_async

from django.utils import timezone as django_timezone
from django.db import models  # Thêm import này
from asgiref.sync import sync_to_async

from .models import Source, Article, FetchLog, AILog
import logging

# Thêm import cho BeautifulSoup
from bs4 import BeautifulSoup

# Thêm import cho gọi API AI
import json
import os
from django.db.models import Q
from django.db import transaction

# Thêm import cho Playwright
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# Thiết lập logger lưu file riêng cho AI/thumbnail
ai_log_path = os.path.join(os.path.dirname(__file__), '../logs/collector_ai.log')
ai_log_path = os.path.abspath(ai_log_path)
os.makedirs(os.path.dirname(ai_log_path), exist_ok=True)
ai_logger = logging.getLogger('collector_ai')
ai_logger.setLevel(logging.INFO)
if not ai_logger.handlers:
    file_handler = logging.FileHandler(ai_log_path, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler.setFormatter(formatter)
    ai_logger.addHandler(file_handler)

# SSL context chuẩn dùng certifi
ssl_context = ssl.create_default_context(cafile=certifi.where())

# Wrappers để gọi ORM an toàn trong async
create_article = sync_to_async(Article.objects.get_or_create, thread_sensitive=True)
update_source_last_fetched = sync_to_async(Source.save, thread_sensitive=True)
create_fetch_log = sync_to_async(FetchLog.objects.create, thread_sensitive=True)
create_ailog = sync_to_async(AILog.objects.create, thread_sensitive=True)


class BaseFetcher:
    """Base class for all fetchers"""

    def __init__(self, source: Source):
        self.source = source

    async def fetch(self) -> List[Dict[str, Any]]:
        """Override this method in subclasses"""
        raise NotImplementedError

    def parse_date(self, date_str: str) -> datetime:
        """Parse RFC-822 or ISO date string to datetime (with tz)."""
        try:
            if not date_str:
                return django_timezone.now()

            # 1) ISO 8601 (e.g. "2025-05-23T21:27:59Z")
            try:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except ValueError:
                pass

            # 2) RFC-822 (e.g. "Fri, 23 May 2025 21:27:59 +0000")
            try:
                return parsedate_to_datetime(date_str)
            except (TypeError, ValueError):
                pass

            # 3) fallback: giờ hiện tại
            return django_timezone.now()

        except Exception as e:
            logger.warning(f"Date parsing failed for '{date_str}': {e}")
            return django_timezone.now()


class RSSFetcher(BaseFetcher):
    """Fetcher for RSS feeds"""

    async def fetch(self) -> List[Dict[str, Any]]:
        articles = []
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                async with session.get(self.source.url) as response:
                    if response.status == 200:
                        xml_data = await response.text()
                        feed = feedparser.parse(xml_data)

                        for item in feed.entries:
                            article_data = {
                                'title': item.get('title', ''),
                                'url': item.get('link', ''),
                                'source': self.source,
                                'published_at': self.parse_date(item.get('published', '')),
                                'summary': item.get('summary', '')
                            }
                            articles.append(article_data)

        except Exception as e:
            logger.error(f"RSS fetch error for {self.source.source}: {e}")
            raise

        return articles


class APIFetcher(BaseFetcher):
    """Fetcher for API endpoints"""

    async def fetch(self) -> List[Dict[str, Any]]:
        articles = []
        params = self.source.params or {}
        headers = params.get('headers', {})

        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                async with session.get(
                    self.source.url,
                    headers=headers,
                    params=params.get('query_params', {})
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        articles = self._parse_api_response(data)

        except Exception as e:
            logger.error(f"API fetch error for {self.source.source}: {e}")
            raise

        return articles

    def _parse_api_response(self, data: Dict) -> List[Dict[str, Any]]:
        articles = []
        items = data.get('items', data.get('articles', data.get('data', [])))

        for item in items:
            article_data = {
                'title': item.get('title', ''),
                'url': item.get('url', item.get('link', '')),
                'source': self.source,
                'published_at': self.parse_date(item.get('published_at', item.get('pubDate', ''))),
                'summary': item.get('summary', item.get('description', ''))
            }
            articles.append(article_data)

        return articles


class AgentQLFetcher(BaseFetcher):
    """Fetcher for static websites using AgentQL"""
    
    async def fetch(self) -> List[Dict[str, Any]]:
        articles = []
        params = self.source.params or {}

        if 'prompt' not in params:
            raise ValueError("AgentQL fetcher requires 'prompt' in params")

        try:
            api_key = await get_agentql_api_key_async()
            payload = {
                "url": self.source.url,
                "prompt": params['prompt']
            }
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": api_key
            }

            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                async with session.post(
                    "https://api.agentql.com/v1/query-data",
                    json=payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        articles = self._parse_agentql_response(result)

        except Exception as e:
            logger.error(f"AgentQL fetch error for {self.source.source}: {e}")
            raise

        return articles

    def _parse_agentql_response(self, result: Dict) -> List[Dict[str, Any]]:
        articles = []
        if result.get('data'):
            first_key = next(iter(result['data'].keys()))
            urls = result['data'][first_key] or []
            for url in urls:
                articles.append({
                    'title': f"Article from {self.source.source}",
                    'url': url,
                    'source': self.source,
                    'published_at': django_timezone.now(),
                    'summary': ''
                })
        return articles


class FetcherFactory:
    """Factory class to create appropriate fetcher"""

    FETCHER_MAP = {
        'rss': RSSFetcher,
        'api': APIFetcher,
        'static': AgentQLFetcher,
    }

    @classmethod
    def create_fetcher(cls, source: Source) -> BaseFetcher:
        fetcher_class = cls.FETCHER_MAP.get(source.type)
        if not fetcher_class:
            raise ValueError(f"Unknown source type: {source.type}")
        return fetcher_class(source)


# Hàm gọi AI để dịch và tóm tắt nội dung sang tiếng Việt
async def call_openrouter_ai(content: str, url: str, ai_type: str = "dev") -> str:
    """
    Giữ tên hàm cũ để tương thích ngược, nhưng hỗ trợ chọn provider/model linh hoạt.

    Cấu hình qua biến môi trường:
    - AI_PROVIDER: "ollama" (mặc định) | "openrouter"
    - AI_MODEL: mặc định "ollama/qwen3:30b-a3b"
      * Với provider=openrouter: truyền model id OpenRouter
      * Với provider=ollama: có thể dùng "ollama/qwen3:30b-a3b" hoặc "qwen3:30b-a3b"
    - OLLAMA_BASE_URL: mặc định "http://127.0.0.1:11434"
    - AI_KNOWLEDGE_LEVEL: beginner | intermediate | advanced (mặc định beginner)
    """
    from .utils import get_openrouter_api_key_async

    provider = (os.getenv("AI_PROVIDER") or "ollama").strip().lower()
    configured_model = (os.getenv("AI_MODEL") or "ollama/qwen3:30b-a3b").strip()
    ollama_base_url = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip('/')
    knowledge_level = (os.getenv("AI_KNOWLEDGE_LEVEL") or "beginner").strip().lower()

    # Chuẩn hoá model cho Ollama (chấp nhận cả prefix ollama/...)
    ollama_model = configured_model
    if ollama_model.startswith("ollama/"):
        ollama_model = ollama_model.split("/", 1)[1]
    # Guard: chỉ từ chối khi nội dung thực sự trống
    if not content or not str(content).strip():
        return f"Tôi không thể phân tích nội dung từ nguồn: {url}."

    # Ưu tiên prompt theo team ai_type để giữ tương thích hành vi cũ
    if ai_type == "dev":
        system_prompt = """Bạn là Senior Engineering Coach, chuyên huấn luyện developer ôn phỏng vấn thực chiến.
Mục tiêu: giúp người học trả lời được câu hỏi interview ở mức triển khai production (không nói lý thuyết chung chung).
Phong cách: rõ ràng, ngắn gọn, thực dụng, có checklist và tình huống vận hành thực tế."""
    elif ai_type == "ba":
        system_prompt = "Bạn là trợ lý AI cho business analyst."
    elif ai_type == "system":
        system_prompt = "Bạn là trợ lý AI cho system admin."
    elif knowledge_level == 'beginner':
        system_prompt = 'Bạn là trợ lý AI cung cấp giải thích đơn giản, dễ hiểu dành cho người mới bắt đầu.'
    elif knowledge_level == 'intermediate':
        system_prompt = 'Bạn là trợ lý AI cung cấp giải thích trung bình cho người có kiến thức trung cấp.'
    elif knowledge_level == 'advanced':
        system_prompt = 'Bạn là trợ lý AI cung cấp giải thích chuyên sâu dành cho người có kiến thức chuyên sâu.'
    else:
        system_prompt = 'Bạn là trợ lý AI.'

    # Giới hạn input để không vượt context của model local (tránh lỗi max_tokens âm)
    content_for_ai = str(content)
    max_chars = int(os.getenv("AI_INPUT_MAX_CHARS", "4500"))
    if len(content_for_ai) > max_chars:
        content_for_ai = content_for_ai[:max_chars] + "\n\n[...Nội dung đã được cắt bớt để phù hợp context model local...]"

    prompt = f"""Dưới đây là nội dung thô tôi cào từ web. Hãy chuyển thành bản ôn luyện PHỎNG VẤN cho Developer (ưu tiên nội dung thực chiến; có thể là backend, testing, debugging, system design, devops hoặc k8s tùy bài gốc).

YÊU CẦU BẮT BUỘC:
- Trả lời bằng tiếng Việt, KHÔNG dùng bảng.
- Không bịa; thiếu dữ liệu thì ghi rõ "Thiếu dữ liệu trong bài gốc".
- Giữ thuật ngữ kỹ thuật gốc theo đúng bài (testing/debugging/backend/system design/devops/k8s...).
- Tập trung vào: bối cảnh triển khai thật, trade-off, lỗi thường gặp, cách debug, và điểm dễ bị hỏi vặn khi phỏng vấn.
- Có dẫn nguồn: {url}

ĐỊNH DẠNG KẾT QUẢ (plain text):
1) [Interview Brief] Tóm tắt 5-7 bullet: bài này giúp trả lời dạng câu hỏi nào.
2) [How to answer in interview] Câu trả lời mẫu 60-120 giây (nói như ứng viên có kinh nghiệm thực tế).
3) [Deep-dive Follow-up] 6-10 câu hỏi vặn sâu + ý trả lời ngắn cho từng câu.
4) [Production Notes] Các thông số/cấu hình thực tế cần nhớ (ports, probes, resources, scaling, logging, monitoring, security) — nếu bài không có thì nêu giả định an toàn.
5) [Troubleshooting] 3-5 sự cố thường gặp + quy trình xử lý từng bước (triage -> kiểm tra -> fix -> phòng ngừa).
6) [Hands-on Task] 1 bài lab nhỏ (30-60 phút) để luyện đúng chủ đề, kèm output mong đợi.
7) [Flashcards] 8-12 thẻ nhớ nhanh theo format: Thuật ngữ: định nghĩa ngắn + khi nào dùng.
8) [Red flags] 3-5 câu trả lời "dở" dễ trượt phỏng vấn và cách sửa.


Nội dung: {content_for_ai}"""

    # Payload chuẩn OpenAI Chat Completions (cả OpenRouter và Ollama /v1 đều dùng được)
    payload = {
        "model": configured_model if provider == "openrouter" else ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ISDNews/1.0.0"
    }

    if provider == "openrouter":
        openrouter_api_key = await get_openrouter_api_key_async()
        if not openrouter_api_key:
            logger.error("OpenRouter API key not found in configuration")
            raise Exception("OpenRouter API key not found in configuration")
        endpoint = "https://openrouter.ai/api/v1/chat/completions"
        headers["Authorization"] = f"Bearer {openrouter_api_key}"
        headers["HTTP-Referer"] = "https://github.com/isdnews"
        logger.info(f"Using OpenRouter endpoint with model: {configured_model}")
    else:
        endpoint = f"{ollama_base_url}/v1/chat/completions"
        logger.info(f"Using Ollama endpoint {endpoint} with model: {ollama_model}")

    try:
        logger.info(f"[AI:{provider}] Gửi prompt cho {url}: {prompt[:500]}...")
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            async with session.post(endpoint, headers=headers, json=payload, timeout=3600) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"[AI:{provider}] Error response {resp.status}: {error_text}")
                    raise Exception(f"{provider} API error: {resp.status} - {error_text}")

                data = await resp.json()
                logger.info(f"[AI:{provider}] Nhận response cho {url}: {str(data)[:500]}...")

                if data.get("choices") and data["choices"][0]["message"].get("content"):
                    result = data["choices"][0]["message"]["content"].strip()
                    logger.info(f"[AI:{provider}] Nội dung dịch cho {url}: {result[:500]}...")

                    def create_log_sync():
                        return AILog.objects.create(
                            url=url,
                            prompt=prompt,
                            response=str(data),
                            result=result,
                            status='success',
                            error_message=''
                        )

                    await asyncio.to_thread(create_log_sync)

                    telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

                    if telegram_bot_token and telegram_chat_id:
                        # Lấy metadata bài viết để tiêu đề Telegram rõ ràng hơn
                        article_title = ''
                        source_name = ''
                        try:
                            def _get_article_meta():
                                a = Article.objects.select_related('source').filter(url=url).order_by('-id').first()
                                if not a:
                                    return ('', '')
                                return (a.title or '', (a.source.source if a.source else ''))
                            article_title, source_name = await asyncio.to_thread(_get_article_meta)
                        except Exception as _meta_err:
                            logger.warning(f"[AI:{provider}] Không lấy được metadata bài viết: {_meta_err}")

                        short_title = (article_title[:90] + '…') if article_title and len(article_title) > 90 else (article_title or 'Bài viết mới')
                        source_tag = f" • {source_name}" if source_name else ''
                        notify_title = f"{short_title}{source_tag}"

                        logger.info(f"[AI:{provider}] Gửi thông báo Telegram cho team {ai_type} cho URL: {url}")
                        await notify_telegram(
                            telegram_bot_token,
                            telegram_chat_id,
                            notify_title,
                            result,
                            url
                        )
                    else:
                        logger.warning("[AI] TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID chưa được cấu hình, bỏ qua thông báo")

                    return result
                else:
                    logger.warning(f"[AI:{provider}] Không nhận được nội dung dịch cho {url}, trả về content gốc.")

                    def create_error_log_sync():
                        return AILog.objects.create(
                            url=url,
                            prompt=prompt,
                            response=str(data),
                            result=content,
                            status='error',
                            error_message='No content from AI'
                        )

                    await asyncio.to_thread(create_error_log_sync)
                    return f"AI_PROCESSING_ERROR: No content from AI for {url}"

    except Exception as e:
        logger.warning(f"Lỗi gọi AI provider {provider}: {e}")
        try:
            error_response = await resp.text() if 'resp' in locals() else ''
        except Exception:
            error_response = ''

        def create_exception_log_sync():
            return AILog.objects.create(
                url=url,
                prompt=prompt,
                response=error_response,
                result=content,
                status='error',
                error_message=str(e)
            )

        await asyncio.to_thread(create_exception_log_sync)
        return f"AI_PROCESSING_ERROR: {str(e)}"


async def fetch_article_detail(url: str) -> Dict[str, str]:
    """
    Dùng Playwright để render trang có JavaScript, đợi load (có bắt timeout),
    sau đó dùng BeautifulSoup trích xuất toàn bộ văn bản (text-only) và ảnh thumbnail.
    Bắt riêng TimeoutError để không dừng khi quá thời gian chờ.
    """
    try:
        # 1. Mở Playwright, đi đến URL và đợi load xong (timeout tăng lên 60000ms)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            logger.info(f"[fetch_article_detail] Đang truy cập URL: {url}")
            
            try:
                #  Tăng timeout lên 60 giây
                await page.goto(url, timeout=60000)
            except PlaywrightTimeoutError:
                logger.warning(f"[fetch_article_detail] Timeout khi page.goto cho {url}, dùng HTML tạm thời.")
            
            try:
                # Đợi networkidle, vẫn giữ timeout mặc định (30 giây) vì phần lớn đã load ở trên
                await page.wait_for_load_state("networkidle")
            except PlaywrightTimeoutError:
                logger.warning(f"[fetch_article_detail] Timeout khi wait_for_load_state cho {url}, tiếp tục với HTML hiện tại.")

            # Đợi thêm selector 'article' (nếu có), timeout 7000ms
            try:
                await page.wait_for_selector('article', timeout=7000)
                logger.info(f"[fetch_article_detail] Selector 'article' đã xuất hiện")
            except PlaywrightTimeoutError:
                logger.warning(f"[fetch_article_detail] Không tìm thấy selector 'article' (timeout) trong trang {url}")
            
            # Đợi thêm 2 giây cho mọi JS chạy xong (nếu còn)
            await page.wait_for_timeout(2000)
            
            # Lấy HTML sau khi render xong (dù có timeout ở trên hay không)
            html = await page.content()
            await browser.close()

        # 2. Phân tích HTML với BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        
        # Loại bỏ các thẻ không cần thiết
        for sel in ["script", "style", "footer", ".ads", ".comments", ".related"]:
            for tag in soup.select(sel):
                tag.decompose()

        # Tìm phần nội dung chính (có thể mở rộng thêm selector nếu cần)
        selectors = ["main", "article", "#content", ".post", ".entry", ".article-body", ".content"]
        root = None
        for sel in selectors:
            root = soup.select_one(sel)
            if root:
                logger.info(f"[fetch_article_detail] Tìm thấy selector nội dung chính: {sel}")
                break
        if not root:
            logger.warning(f"[fetch_article_detail] Không tìm thấy selector nội dung chính, dùng toàn bộ trang {url}")
            root = soup

        # Lấy title và meta description (nếu tồn tại)
        title = soup.title.string.strip() if soup.title else ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        meta = meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else ""

        # Lấy toàn bộ văn bản từ root
        full_text = root.get_text(separator="\n", strip=True)
        if title:
            full_text = f"{title}\n\n{full_text}"
        if meta:
            full_text = f"{full_text}\n\n{meta}"

        # Loại bỏ dòng trống
        lines = [line for line in full_text.splitlines() if line.strip()]
        raw_content = "\n".join(lines)

        logger.info(f"[fetch_article_detail] Độ dài nội dung thô: {len(raw_content)}")
        logger.debug(f"[fetch_article_detail] Đoạn nội dung thô (500 ký tự đầu): {raw_content[:500]}")

        # 3. Lấy thumbnail: ưu tiên meta og:image, nếu không có thì ảnh đầu tiên trong root
        thumbnail = ""
        ogimg = soup.find("meta", property="og:image")
        if ogimg and ogimg.get("content"):
            thumbnail = ogimg["content"]
            logger.info(f"[fetch_article_detail] Thumbnail og:image cho {url}: {thumbnail}")
        else:
            img_tag = root.find("img") if root else None
            if img_tag and img_tag.get("src"):
                thumbnail = img_tag["src"]
                logger.info(f"[fetch_article_detail] Thumbnail ảnh đầu tiên trong nội dung cho {url}: {thumbnail}")
            else:
                img_tag2 = soup.find("img")
                if img_tag2 and img_tag2.get("src"):
                    thumbnail = img_tag2["src"]
                    logger.info(f"[fetch_article_detail] Thumbnail ảnh đầu tiên trong trang cho {url}: {thumbnail}")

        # 4. Trả về raw_content và thumbnail
        return {"content": raw_content, "thumbnail": thumbnail}

    except Exception as e:
        logger.error(f"[fetch_article_detail] Lỗi khi cào chi tiết cho {url}: {e}")
        return {"content": "", "thumbnail": ""}
class DataCollector:
    """Main collector class to orchestrate fetching"""

    async def collect_from_source(self, source: Source) -> Dict[str, Any]:
        start_time = time.time()
        log_data = {
            'source': source,
            'status': 'error',
            'articles_count': 0,
            'error_message': '',
            'execution_time': 0
        }

        try:
            # Tạo fetcher tương ứng với source (rss, api, static)
            fetcher = FetcherFactory.create_fetcher(source)
            # Lấy danh sách bài từ fetcher
            articles_data = await fetcher.fetch()

            # Lọc các URL đã tồn tại trong Article, chỉ lấy tối đa 5 bài mới
            existing_urls = set(
                await sync_to_async(list)(
                    Article.objects.filter(url__in=[a['url'] for a in articles_data])
                                   .values_list('url', flat=True)
                )
            )
            new_articles = [a for a in articles_data if a['url'] not in existing_urls][:5]

            saved_count = 0
            for data in new_articles:
                try:
                    # Tạo Article mới với content và thumbnail tạm thời là rỗng
                    article_obj, created = await create_article(
                        url=data['url'],
                        defaults={
                            'title': data['title'],
                            'source': source,
                            'published_at': data['published_at'],
                            'summary': data.get('summary', ''),
                            'content': '',       # sẽ cào chi tiết ngay sau
                            'thumbnail': '',     # sẽ cào chi tiết ngay sau
                            'is_ai_processed': False,
                            'ai_type': '',
                            'ai_content': '',
                        }
                    )

                    if created:
                        # Nếu mới tạo, cào chi tiết nội dung và thumbnail
                        detail = await fetch_article_detail(data['url'])
                        article_obj.content = detail.get("content", "")
                        article_obj.thumbnail = detail.get("thumbnail", "")
                        
                        # Lưu lại Article (thao tác Django ORM phải chạy đồng bộ)
                        def save_article_sync():
                            article_obj.save(update_fields=['content', 'thumbnail'])
                        await asyncio.to_thread(save_article_sync)

                    saved_count += 1
                    # Tạm nghỉ 2 giây giữa mỗi bài để tránh quá tải
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Error saving or crawling detail for {data.get('url')}: {e}")
                    continue

            # Sau khi xử lý xong, cập nhật last_fetched của source
            source.last_fetched = django_timezone.now()
            await update_source_last_fetched(source, update_fields=['last_fetched'])

            log_data.update({
                'status': 'success',
                'articles_count': saved_count,
            })

        except Exception as e:
            log_data.update({
                'error_message': str(e),
                'status': 'error'
            })
            logger.error(f"Collection failed for {source.source}: {e}")

        finally:
            log_data['execution_time'] = time.time() - start_time
            # Ghi FetchLog
            await create_fetch_log(**log_data)

        return log_data
    
    async def collect_all_active_sources(self, team_code: Optional[str] = None):
        now = django_timezone.now()
        queryset = Source.objects.filter(is_active=True)

        if team_code:
            queryset = queryset.filter(team__code=team_code)

        # Lọc các nguồn có force_collect=True hoặc đã đến thời gian thu thập
        queryset = queryset.filter(
            models.Q(force_collect=True) |
            models.Q(last_fetched__isnull=True) |
            models.Q(last_fetched__lte=now - models.F('fetch_interval') * timedelta(seconds=1))
        )

        active_sources = await sync_to_async(list)(queryset)

        if active_sources:
            tasks = [self.collect_from_source(src) for src in active_sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'success')
            total_articles = sum(r.get('articles_count', 0) for r in results if isinstance(r, dict))
            logger.info(f"Collection completed: {success_count}/{len(tasks)} sources successful, {total_articles} new articles")
            return results
        return []


async def notify_telegram(bot_token: str, chat_id: str, title: str, content: str, url: str = None):
    """
    Gửi thông báo đến Telegram Bot API
    """
    if not bot_token or not chat_id:
        logger.warning("[Telegram] Bot token hoặc chat ID không được cung cấp, bỏ qua thông báo")
        return
    
    # Format nội dung cho Telegram (hỗ trợ Markdown)
    message = f"*{title}*\n\n{content}"
    if url:
        message += f"\n\n🔗 [Xem bài viết]({url})"
    
    # Giới hạn độ dài tin nhắn Telegram (4096 ký tự)
    if len(message) > 4096:
        message = message[:4000] + "\n\n... (nội dung đã được cắt gọn)"
    
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }

    try:
        logger.info(f"[Telegram] Đang gửi thông báo đến chat {chat_id}...")
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            async with session.post(api_url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    logger.info("[Telegram] Đã gửi thông báo thành công (Markdown)")
                    return

                error_text = await resp.text()
                logger.error(f"[Telegram] Lỗi gửi Markdown. Status: {resp.status}, Response: {error_text}")

                # Fallback: gửi plain text nếu lỗi parse Markdown/entity
                fallback_payload = {
                    "chat_id": chat_id,
                    "text": message,
                    "disable_web_page_preview": False
                }
                async with session.post(api_url, json=fallback_payload, timeout=30) as resp2:
                    if resp2.status == 200:
                        logger.info("[Telegram] Fallback plain text gửi thành công")
                    else:
                        error_text2 = await resp2.text()
                        logger.error(f"[Telegram] Fallback cũng lỗi. Status: {resp2.status}, Response: {error_text2}")
    except Exception as e:
        logger.error(f"[Telegram] Lỗi khi gửi thông báo: {str(e)}")
        logger.exception("[Telegram] Chi tiết lỗi:")


async def notify_teams(flow_url: str, title: str, content: str, url: str = None, sender: str = "Bot Notify"):
    """
    Gửi thông báo đến Microsoft Teams qua Power Automate với format đẹp
    (DEPRECATED - Không còn sử dụng, giữ lại để tương thích ngược)
    """
    
    def format_content_for_teams(content: str) -> str:
        """Format nội dung cho Teams với markdown"""
        
        # Loại bỏ HTML tags nếu có
        content = re.sub(r'<[^>]+>', '', content)
        
        # Decode HTML entities
        content = html.unescape(content)
        
        # Thay thế markdown cơ bản
        content = re.sub(r'\*\*(.*?)\*\*', r'**\1**', content)  # Bold
        content = re.sub(r'\*(.*?)\*', r'*\1*', content)        # Italic
        content = re.sub(r'```(.*?)```', r'`\1`', content, flags=re.DOTALL)  # Code blocks
        content = re.sub(r'`(.*?)`', r'`\1`', content)         # Inline code
        
        # Xử lý danh sách
        content = re.sub(r'^- ', '• ', content, flags=re.MULTILINE)
        content = re.sub(r'^\d+\. ', '1. ', content, flags=re.MULTILINE)
        
        # Xử lý headers
        content = re.sub(r'^### (.*?)$', r'**\1**', content, flags=re.MULTILINE)
        content = re.sub(r'^## (.*?)$', r'**\1**', content, flags=re.MULTILINE)
        content = re.sub(r'^# (.*?)$', r'**\1**', content, flags=re.MULTILINE)
        
        # Xử lý links
        content = re.sub(r'\[(.*?)\]\((.*?)\)', r'[\1](\2)', content)
        
        # Loại bỏ các dòng trống thừa
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        # Giới hạn độ dài nếu quá dài
        if len(content) > 4000:
            content = content[:3800] + "\n\n... (nội dung đã được cắt gọn)"
        
        return content.strip()
    
    def create_summary(content: str, max_length: int = 200) -> str:
        """Tạo tóm tắt ngắn gọn"""
        # Lấy đoạn đầu tiên
        first_paragraph = content.split('\n\n')[0]
        
        if len(first_paragraph) <= max_length:
            return first_paragraph
        
        # Cắt tại từ cuối cùng
        words = first_paragraph.split()
        summary = ""
        for word in words:
            if len(summary + word + " ") <= max_length - 3:
                summary += word + " "
            else:
                break
        
        return summary.strip() + "..."
    
    # Format nội dung
    formatted_content = format_content_for_teams(content)
    
    # Tạo tóm tắt ngắn cho title nếu cần
    if len(title) > 100:
        title = title[:97] + "..."
    
    # Tạo payload
    payload = {
        "title": title,
        "message": formatted_content,
        "url": url or "",
        "sender": sender,
        "summary": create_summary(formatted_content)  # Thêm tóm tắt
    }
    
    try:
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                flow_url,
                json=payload,
                headers={
                    'Content-Type': 'application/json'
                }
            ) as response:
                if response.status == 200:
                    return {"status": "success", "message": "Đã gửi thành công"}
                else:
                    return {"status": "error", "message": f"Lỗi HTTP: {response.status}"}
                    
    except Exception as e:
        return {"status": "error", "message": f"Lỗi: {str(e)}"}
    # """Gửi thông báo đến Microsoft Teams thông qua Power Automate Flow"""
    # logger.info(f"[Teams] Preparing to send notification...")
    # logger.info(f"[Teams] Flow URL: {flow_url[:50]}...")
    # logger.info(f"[Teams] Title: {title}")
    # logger.info(f"[Teams] URL: {url}")
    # logger.info(f"[Teams] Content length: {len(content)} characters")
    # logger.info(f"[Teams] Sender: {sender}")

    # if not flow_url:
    #     logger.warning("[Teams] No Flow URL provided, skipping notification")
    #     return

    # try:
    #     # Payload theo format Power Automate Flow
    #     payload = {
    #         "title": title,
    #         "message": content,
    #         "sender": sender,
    #         "url": url if url else "",
    #         "timestamp": None  # Flow sẽ tự generate timestamp
    #     }
        
    #     headers = {
    #         'Content-Type': 'application/json'
    #     }

    #     logger.info("[Teams] Sending request to Power Automate Flow...")
    #     logger.debug(f"[Teams] Payload: {json.dumps(payload, indent=2)}")
        
    #     # Sử dụng aiohttp để gữi async request
    #     async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context())) as session:
    #         async with session.post(flow_url, json=payload, headers=headers) as resp:
    #             response_text = await resp.text()
                
    #             if resp.status == 200:
    #                 logger.info("[Teams] Successfully sent notification to Teams via Flow")
    #                 logger.debug(f"[Teams] Response: {response_text}")
    #             elif resp.status == 202:
    #                 logger.info("[Teams] Flow accepted the request (202 Accepted)")
    #                 logger.debug(f"[Teams] Response: {response_text}")
    #             else:
    #                 logger.error(f"[Teams] Error sending notification. Status: {resp.status}")
    #                 logger.error(f"[Teams] Error response: {response_text}")
                    
    # except aiohttp.ClientError as e:
    #     logger.error(f"[Teams] HTTP Client error: {str(e)}")
    #     logger.exception("[Teams] Full exception:")
    # except Exception as e:
    #     logger.error(f"[Teams] Failed to send notification: {str(e)}")
    #     logger.exception("[Teams] Full exception:")