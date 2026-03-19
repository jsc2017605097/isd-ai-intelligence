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

from .utils import get_agentql_api_key_async, get_openrouter_api_key_async

from django.utils import timezone as django_timezone
from django.db import models
from asgiref.sync import sync_to_async

from .models import Source, Article, FetchLog, AILog, SystemConfig, Team
import logging

from bs4 import BeautifulSoup
import json
import os
from django.db.models import Q
from django.db import transaction
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

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

ssl_context = ssl.create_default_context(cafile=certifi.where())

create_article = sync_to_async(Article.objects.get_or_create, thread_sensitive=True)
update_source_last_fetched = sync_to_async(Source.save, thread_sensitive=True)
create_fetch_log = sync_to_async(FetchLog.objects.create, thread_sensitive=True)
create_ailog = sync_to_async(AILog.objects.create, thread_sensitive=True)

class BaseFetcher:
    def __init__(self, source: Source):
        self.source = source
    async def fetch(self) -> List[Dict[str, Any]]:
        raise NotImplementedError
    def parse_date(self, date_str: str) -> datetime:
        try:
            if not date_str: return django_timezone.now()
            try: return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except ValueError: pass
            try: return parsedate_to_datetime(date_str)
            except (TypeError, ValueError): pass
            return django_timezone.now()
        except Exception as e:
            logger.warning(f"Date parsing failed for '{date_str}': {e}")
            return django_timezone.now()

class RSSFetcher(BaseFetcher):
    async def fetch(self) -> List[Dict[str, Any]]:
        articles = []
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                async with session.get(self.source.url) as response:
                    if response.status == 200:
                        xml_data = await response.text()
                        feed = feedparser.parse(xml_data)
                        for item in feed.entries:
                            articles.append({
                                'title': item.get('title', ''),
                                'url': item.get('link', ''),
                                'source': self.source,
                                'published_at': self.parse_date(item.get('published', '')),
                                'summary': item.get('summary', '')
                            })
        except Exception as e:
            logger.error(f"RSS fetch error: {e}")
        return articles

class FetcherFactory:
    FETCHER_MAP = {'rss': RSSFetcher}
    @classmethod
    def create_fetcher(cls, source: Source) -> BaseFetcher:
        fetcher_class = cls.FETCHER_MAP.get(source.type)
        if not fetcher_class: raise ValueError(f"Unknown source type: {source.type}")
        return fetcher_class(source)

async def call_openrouter_ai(content: str, url: str, ai_type: str = "dev") -> str:
    provider = (os.getenv("AI_PROVIDER") or "ollama").strip().lower()
    configured_model = (os.getenv("AI_MODEL") or "qwen3:30b-a3b").strip()
    api_key = os.getenv("AI_API_KEY")
    base_url = os.getenv("AI_BASE_URL")
    
    logger.info(f"[{ai_type}] Starting AI Job | Vendor: {provider.upper()} | Model: {configured_model}")

    if not content or not str(content).strip():
        return f"Cannot analyze content from source: {url}."

    # 1. Fetch System Prompt from Database
    try:
        def _get_team_prompt():
            team = Team.objects.filter(code=ai_type, is_active=True).first()
            return team.system_prompt if team and team.system_prompt else None
        custom_system_prompt = await asyncio.to_thread(_get_team_prompt)
    except Exception as _p_err:
        logger.warning(f"Error fetching team prompt: {_p_err}")
        custom_system_prompt = None

    # Default logic if no custom prompt exists
    if custom_system_prompt:
        system_prompt = custom_system_prompt
    else:
        # Fallback to the old default behavior (Interview Prep)
        system_prompt = f"""You are a professional assistant. Convert the raw content provided into a high-quality guide.
Response language: Vietnamese.
If this is for team 'dev', focus on production implementation, trade-offs, and debugging in an INTERVIEW PREP format.
"""

    content_for_ai = str(content)
    max_chars = int(os.getenv("AI_INPUT_MAX_CHARS", "4500"))
    if len(content_for_ai) > max_chars:
        content_for_ai = content_for_ai[:max_chars] + "\n\n[...Content truncated...]"

    # User Prompt is now just the task and data, instructions are in System Prompt
    user_prompt = f"Original Source: {url}\n\nRaw Content to process:\n{content_for_ai}"

    endpoint = ""
    headers = {"Content-Type": "application/json", "User-Agent": "ISDNews/1.0.0"}
    payload = {}

    if provider == "openai":
        endpoint = (base_url or "https://api.openai.com/v1") + "/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        payload = {"model": configured_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
    elif provider == "ollama":
        base = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip('/')
        endpoint = f"{base}/api/chat"
        payload = {"model": configured_model, "stream": False, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
    elif provider == "google":
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{configured_model}:generateContent?key={api_key}"
        payload = {"contents": [{"role": "user", "parts": [{"text": f"System Instructions: {system_prompt}\n\nUser Data: {user_prompt}"}]}]}
    elif provider == "openrouter":
        endpoint = "https://openrouter.ai/api/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key or await get_openrouter_api_key_async()}"
        payload = {"model": configured_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
    else:
        # Default OpenAI-compatible
        base = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip('/')
        endpoint = f"{base}/v1/chat/completions"
        payload = {"model": configured_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}

    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            async with session.post(endpoint, headers=headers, json=payload, timeout=300) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    raise Exception(f"AI Error {resp.status}: {err_text}")
                data = await resp.json()
                result = ""
                if "choices" in data: result = data["choices"][0]["message"]["content"]
                elif "message" in data: result = data["message"]["content"]
                elif "candidates" in data: result = data["candidates"][0]["content"]["parts"][0]["text"]
                
                result = result.strip()
                await create_ailog(url=url, prompt=user_prompt, response=str(data), result=result, status='success', error_message='')
                
                # Notify Telegram
                bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                chat_id = os.getenv('TELEGRAM_CHAT_ID')
                try:
                    def _get_team_chat():
                        c = SystemConfig.objects.filter(key='telegram_chat_id', team__code=ai_type, is_active=True).first()
                        return c.value if c else None
                    team_cid = await asyncio.to_thread(_get_team_chat)
                    if team_cid: chat_id = team_cid
                except: pass

                if bot_token and chat_id:
                    def _get_meta():
                        a = Article.objects.select_related('source').filter(url=url).order_by('-id').first()
                        return (a.title, a.source.source) if a else ("New Article", "")
                    title, source = await asyncio.to_thread(_get_meta)
                    await notify_telegram(bot_token, chat_id, f"{title[:90]} • {source}", result, url)
                return result
    except Exception as e:
        logger.warning(f"AI Call failed: {e}")
        return f"AI_PROCESSING_ERROR: {str(e)}"

async def fetch_article_detail(url: str) -> Dict[str, str]:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=60000)
                await page.wait_for_load_state("networkidle")
            except: pass
            html = await page.content()
            await browser.close()
        soup = BeautifulSoup(html, "html.parser")
        for s in ["script", "style", "footer", ".ads"]:
            for t in soup.select(s): t.decompose()
        root = next((soup.select_one(s) for s in ["main", "article", "#content", ".content"] if soup.select_one(s)), soup)
        return {"content": root.get_text(separator="\n", strip=True), "thumbnail": (soup.find("meta", property="og:image") or {"content":""})["content"]}
    except: return {"content": "", "thumbnail": ""}

class DataCollector:
    async def collect_from_source(self, source: Source) -> Dict[str, Any]:
        start = time.time()
        res = {'source': source, 'status': 'error', 'articles_count': 0}
        try:
            data = await RSSFetcher(source).fetch()
            existing = set(await sync_to_async(list)(Article.objects.filter(url__in=[a['url'] for a in data]).values_list('url', flat=True)))
            # Lấy limit từ JobConfig
            def _get_crawl_limit():
                from .models import JobConfig
                cfg = JobConfig.objects.filter(job_type='crawl').first()
                return cfg.limit if cfg else 5
            
            crawl_limit = await asyncio.to_thread(_get_crawl_limit)
            news = [a for a in data if a['url'] not in existing][:crawl_limit]
            for item in news:
                art, created = await create_article(url=item['url'], defaults={'title': item['title'], 'source': source, 'published_at': item['published_at'], 'summary': item.get('summary', '')})
                if created:
                    det = await fetch_article_detail(item['url'])
                    art.content, art.thumbnail = det['content'], det['thumbnail']
                    await asyncio.to_thread(art.save)
                await asyncio.sleep(1)
            source.last_fetched = django_timezone.now()
            await update_source_last_fetched(source, update_fields=['last_fetched'])
            res.update({'status': 'success', 'articles_count': len(news)})
        except Exception as e: res.update({'error_message': str(e)})
        finally:
            res['execution_time'] = time.time() - start
            await create_fetch_log(**res)
        return res
    async def collect_all_active_sources(self, team_code: Optional[str] = None):
        qs = Source.objects.filter(is_active=True)
        if team_code: qs = qs.filter(team__code=team_code)
        due = qs.filter(Q(force_collect=True) | Q(last_fetched__isnull=True) | Q(last_fetched__lte=django_timezone.now() - models.F('fetch_interval') * timedelta(seconds=1)))
        active = await sync_to_async(list)(due)
        if active: return await asyncio.gather(*[self.collect_from_source(s) for s in active], return_exceptions=True)
        return []

async def notify_telegram(token, chat_id, title, content, url=None):
    if not token or not chat_id: return
    msg = f"*{title}*\n\n{content}"
    if url: msg += f"\n\n🔗 [View]({url})"
    if len(msg) > 4096: msg = msg[:4000] + "..."
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as s:
        async with s.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}) as r:
            if r.status != 200: await s.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": msg})
