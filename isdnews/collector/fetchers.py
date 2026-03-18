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

# BeautifulSoup for content extraction
from bs4 import BeautifulSoup

import json
import os
from django.db.models import Q
from django.db import transaction

# Playwright for dynamic web scraping
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# Configure AI loggers
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

# ORM Wrappers
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
            if not date_str:
                return django_timezone.now()
            try:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except ValueError:
                pass
            try:
                return parsedate_to_datetime(date_str)
            except (TypeError, ValueError):
                pass
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
    async def fetch(self) -> List[Dict[str, Any]]:
        articles = []
        params = self.source.params or {}
        if 'prompt' not in params:
            raise ValueError("AgentQL fetcher requires 'prompt' in params")
        try:
            api_key = await get_agentql_api_key_async()
            payload = {"url": self.source.url, "prompt": params['prompt']}
            headers = {"Content-Type": "application/json", "X-API-Key": api_key}
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                async with session.post("https://api.agentql.com/v1/query-data", json=payload, headers=headers) as response:
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
    FETCHER_MAP = {'rss': RSSFetcher, 'api': APIFetcher, 'static': AgentQLFetcher}
    @classmethod
    def create_fetcher(cls, source: Source) -> BaseFetcher:
        fetcher_class = cls.FETCHER_MAP.get(source.type)
        if not fetcher_class:
            raise ValueError(f"Unknown source type: {source.type}")
        return fetcher_class(source)

async def call_openrouter_ai(content: str, url: str, ai_type: str = "dev") -> str:
    """Unified LLM call supporting multiple providers and authentication methods"""
    provider = (os.getenv("AI_PROVIDER") or "ollama").strip().lower()
    configured_model = (os.getenv("AI_MODEL") or "qwen3:30b-a3b").strip()
    auth_method = os.getenv("AI_AUTH_METHOD", "apikey")
    api_key = os.getenv("AI_API_KEY")
    base_url = os.getenv("AI_BASE_URL")
    
    # OAuth Fields (reserved for future/manual token usage)
    client_id = os.getenv("AI_CLIENT_ID")
    client_secret = os.getenv("AI_CLIENT_SECRET")
    refresh_token = os.getenv("AI_REFRESH_TOKEN")

    if auth_method == "oauth" and provider == "google":
        # Placeholder for real OAuth token refresh logic
        # In a real app, you'd use client_id/secret/refresh_token to get a new access_token
        # For now, we'll assume the user might have provided a short-lived token in AI_API_KEY 
        # or we'd need a helper function here.
        pass

    knowledge_level = (os.getenv("AI_KNOWLEDGE_LEVEL") or "beginner").strip().lower()

    if not content or not str(content).strip():
        return f"Cannot analyze content from source: {url}."

    # Prompt Engineering (Senior Engineering Coach)
    if ai_type == "dev":
        system_prompt = "You are a Senior Engineering Coach, specializing in developer interview prep."
    elif ai_type == "ba":
        system_prompt = "You are a Senior Business Analyst Coach."
    elif ai_type == "system":
        system_prompt = "You are a Senior Systems Architect."
    else:
        system_prompt = f"You are a professional assistant for level: {knowledge_level}."

    content_for_ai = str(content)
    max_chars = int(os.getenv("AI_INPUT_MAX_CHARS", "4500"))
    if len(content_for_ai) > max_chars:
        content_for_ai = content_for_ai[:max_chars] + "\n\n[...Content truncated for context limits...]"

    prompt = f"""Convert the following raw content into a high-quality INTERVIEW PREP guide for Developers.
Focus on: Production implementation, trade-offs, common pitfalls, and debugging.
Response language: Vietnamese.
Original Source: {url}

FORMAT:
1) [Interview Brief] Summary of what interview questions this helps with.
2) [How to answer in interview] A model answer (60-120 seconds).
3) [Deep-dive Follow-up] 5-8 tricky follow-up questions and concise answers.
4) [Production Notes] Real-world config/metrics to remember.
5) [Troubleshooting] 3-5 common incidents and steps to fix.

Content: {content_for_ai}"""

    # Provider Handling
    endpoint = ""
    headers = {"Content-Type": "application/json", "User-Agent": "ISDNews/1.0.0"}
    payload = {}

    if provider == "openrouter":
        endpoint = "https://openrouter.ai/api/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key or await get_openrouter_api_key_async()}"
        payload = {"model": configured_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]}
    elif provider == "openai":
        endpoint = (base_url or "https://api.openai.com/v1") + "/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        payload = {"model": configured_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]}
    elif provider == "anthropic":
        endpoint = (base_url or "https://api.anthropic.com/v1") + "/messages"
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        payload = {"model": configured_model, "system": system_prompt, "messages": [{"role": "user", "content": prompt}], "max_tokens": 4096}
    elif provider == "google":
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{configured_model}:generateContent?key={api_key}"
        payload = {"contents": [{"role": "user", "parts": [{"text": f"System: {system_prompt}\n\nUser: {prompt}"}]}]}
    else: # Ollama / vLLM
        style = os.getenv("LLM_API_STYLE", "ollama")
        base = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip('/')
        if style == "openai" or style == "vllm":
            endpoint = f"{base}/v1/chat/completions"
            payload = {"model": configured_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]}
        else:
            endpoint = f"{base}/api/chat"
            payload = {"model": configured_model, "stream": False, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]}

    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            async with session.post(endpoint, headers=headers, json=payload, timeout=300) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    raise Exception(f"{provider} API Error {resp.status}: {err_text}")
                
                data = await resp.json()
                result = ""
                if provider == "anthropic":
                    result = data["content"][0]["text"]
                elif provider == "google":
                    result = data["candidates"][0]["content"]["parts"][0]["text"]
                else: # OpenAI style
                    if "choices" in data:
                        result = data["choices"][0]["message"]["content"]
                    elif "message" in data:
                        result = data["message"]["content"]
                
                result = result.strip()
                
                # Log success
                await create_ailog(url=url, prompt=prompt, response=str(data), result=result, status='success', error_message='')
                
                # Notify Telegram
                bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                chat_id = os.getenv('TELEGRAM_CHAT_ID')
                
                # Check for per-team chat ID in Database
                try:
                    def _get_team_chat_id():
                        cfg = SystemConfig.objects.filter(key='telegram_chat_id', team__code=ai_type, is_active=True).first()
                        return cfg.value if cfg else None
                    team_chat_id = await asyncio.to_thread(_get_team_chat_id)
                    if team_chat_id:
                        chat_id = team_chat_id
                        logger.info(f"[AI:{provider}] Using per-team chat ID: {chat_id} for team {ai_type}")
                except Exception as _cfg_err:
                    logger.warning(f"Error looking up team chat ID: {_cfg_err}")

                if bot_token and chat_id:
                    # Get metadata for better title
                    def _get_meta():
                        a = Article.objects.select_related('source').filter(url=url).order_by('-id').first()
                        return (a.title, a.source.source) if a else ("New Article", "")
                    title, source = await asyncio.to_thread(_get_meta)
                    notify_title = f"{title[:90]} • {source}"
                    await notify_telegram(bot_token, chat_id, notify_title, result, url)

                return result

    except Exception as e:
        logger.warning(f"LLM Call failed ({provider}): {e}")
        await create_ailog(url=url, prompt=prompt, response='', result='', status='error', error_message=str(e))
        return f"AI_PROCESSING_ERROR: {str(e)}"

async def fetch_article_detail(url: str) -> Dict[str, str]:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=60000)
                await page.wait_for_load_state("networkidle")
            except PlaywrightTimeoutError:
                pass
            html_content = await page.content()
            await browser.close()

        soup = BeautifulSoup(html_content, "html.parser")
        for sel in ["script", "style", "footer", ".ads", ".comments"]:
            for tag in soup.select(sel): tag.decompose()

        selectors = ["main", "article", "#content", ".content", ".post"]
        root = next((soup.select_one(s) for s in selectors if soup.select_one(s)), soup)
        
        text = root.get_text(separator="\n", strip=True)
        # Simple thumbnail logic
        img = soup.find("meta", property="og:image")
        thumb = img["content"] if img else ""
        
        return {"content": text, "thumbnail": thumb}
    except Exception as e:
        logger.error(f"Scrape failed for {url}: {e}")
        return {"content": "", "thumbnail": ""}

class DataCollector:
    async def collect_from_source(self, source: Source) -> Dict[str, Any]:
        start = time.time()
        res = {'source': source, 'status': 'error', 'articles_count': 0, 'error_message': '', 'execution_time': 0}
        try:
            fetcher = FetcherFactory.create_fetcher(source)
            data = await fetcher.fetch()
            existing = set(await sync_to_async(list)(Article.objects.filter(url__in=[a['url'] for a in data]).values_list('url', flat=True)))
            news = [a for a in data if a['url'] not in existing][:5]
            
            for item in news:
                art, created = await create_article(url=item['url'], defaults={
                    'title': item['title'], 'source': source, 'published_at': item['published_at'],
                    'summary': item.get('summary', ''), 'content': '', 'thumbnail': '',
                    'is_ai_processed': False, 'ai_type': '', 'ai_content': ''
                })
                if created:
                    detail = await fetch_article_detail(item['url'])
                    art.content = detail['content']
                    art.thumbnail = detail['thumbnail']
                    await asyncio.to_thread(art.save, update_fields=['content', 'thumbnail'])
                await asyncio.sleep(1)
            
            source.last_fetched = django_timezone.now()
            await update_source_last_fetched(source, update_fields=['last_fetched'])
            res.update({'status': 'success', 'articles_count': len(news)})
        except Exception as e:
            res.update({'error_message': str(e)})
        finally:
            res['execution_time'] = time.time() - start
            await create_fetch_log(**res)
        return res

    async def collect_all_active_sources(self, team_code: Optional[str] = None):
        qs = Source.objects.filter(is_active=True)
        if team_code: qs = qs.filter(team__code=team_code)
        due = qs.filter(Q(force_collect=True) | Q(last_fetched__isnull=True) | Q(last_fetched__lte=django_timezone.now() - models.F('fetch_interval') * timedelta(seconds=1)))
        active = await sync_to_async(list)(due)
        if active:
            tasks = [self.collect_from_source(s) for s in active]
            return await asyncio.gather(*tasks, return_exceptions=True)
        return []

async def notify_telegram(token, chat_id, title, content, url=None):
    if not token or not chat_id: return
    msg = f"*{title}*\n\n{content}"
    if url: msg += f"\n\n🔗 [View Article]({url})"
    if len(msg) > 4096: msg = msg[:4000] + "\n\n...(truncated)"
    
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as sess:
        # Try Markdown
        async with sess.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}) as r:
            if r.status == 200: return
            # Fallback Plain
            await sess.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": msg})
