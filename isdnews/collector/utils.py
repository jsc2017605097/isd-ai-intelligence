from typing import Optional
from .models import SystemConfig, Team
from django.core.cache import cache
import logging
import asyncio

logger = logging.getLogger(__name__)

from asgiref.sync import sync_to_async


# Helper sync functions để gọi trong async context
def get_system_config_sync(key: str, team: Optional[str] = None):
    try:
        query = SystemConfig.objects.filter(key=key, is_active=True)
        if team:
            query = query.filter(team=team)
        return query.first()
    except Exception as e:
        logger.error(f"Error getting system config {key}: {e}")
        return None


async def get_system_config_async(key: str, team: Optional[str] = None, cache_timeout: int = 300) -> Optional[str]:
    cache_key = f"system_config:{key}:{team}" if team else f"system_config:{key}"
    
    value = cache.get(cache_key)
    if value is not None:
        return value
        
    # Tạo hàm đồng bộ để lấy config
    def get_config_sync():
        try:
            query = SystemConfig.objects.filter(key=key, is_active=True)
            if team:
                query = query.filter(team=team)
            config = query.first()
            if config:
                value = config.value.strip() if config.value else ''
                cache.set(cache_key, value, cache_timeout)
                return value
            return None
        except Exception as e:
            logger.error(f"Error getting system config {key}: {e}")
            return None

    # Gọi hàm đồng bộ trong thread riêng
    return await asyncio.to_thread(get_config_sync)


def get_system_config(key: str, team: Optional[str] = None, cache_timeout: int = 300) -> Optional[str]:
    cache_key = f"system_config:{key}:{team}" if team else f"system_config:{key}"
    
    value = cache.get(cache_key)
    if value is not None:
        return value
        
    try:
        config = get_system_config_sync(key, team)
        if config:
            value = config.value.strip() if config.value else ''
            cache.set(cache_key, value, cache_timeout)
            return value
    except Exception as e:
        logger.error(f"Error getting system config {key}: {e}")
    
    return None


def get_config_value(key: str, team: str = None) -> str:
    cache_key = f"system_config:{key}:{team}" if team else f"system_config:{key}"
    value = cache.get(cache_key)
    
    if value is None:
        try:
            config = get_system_config_sync(key, team)
            value = config.value if config else None
            cache.set(cache_key, value, 300)
        except Exception as e:
            logger.error(f"Error getting config {key}: {e}")
            return None
            
    return value


def get_teams_webhook_sync(team_code: str) -> Optional[str]:
    try:
        team = Team.objects.get(code=team_code, is_active=True)
        config = SystemConfig.objects.filter(
            key='teams_webhook',
            team=team,
            is_active=True
        ).first()
        return config.value if config else None
    except Team.DoesNotExist:
        logger.error(f"Team with code {team_code} not found")
        return None
    except Exception as e:
        logger.error(f"Error getting teams webhook: {str(e)}")
        return None


async def get_teams_webhook_async(team_code: str) -> Optional[str]:
    try:
        # Tạo hàm đồng bộ để lấy webhook
        def get_webhook_sync():
            try:
                team = Team.objects.get(code=team_code, is_active=True)
                config = SystemConfig.objects.filter(
                    key='teams_webhook',
                    team=team,
                    is_active=True
                ).first()
                return config.value if config else None
            except Team.DoesNotExist:
                logger.error(f"Team with code {team_code} not found")
                return None
            except Exception as e:
                logger.error(f"Error getting teams webhook: {str(e)}")
                return None

        # Gọi hàm đồng bộ trong thread riêng
        return await asyncio.to_thread(get_webhook_sync)
    except Exception as e:
        logger.error(f"Error in get_teams_webhook_async: {str(e)}")
        return None


async def get_openrouter_api_key_async() -> str:
    key = await get_system_config_async('openrouter_api_key')
    if not key:
        logger.error("OpenRouter API key not configured")
        return ""
    
    key = key.strip()
    if not key.startswith('sk-or-'):
        logger.error(f"Invalid OpenRouter API key format: {key[:10]}...")
        return ""
        
    return key


def get_openrouter_api_key() -> str:
    key = get_system_config('openrouter_api_key')
    if not key:
        logger.error("OpenRouter API key not configured")
        return ""
    
    key = key.strip()
    if not key.startswith('sk-or-'):
        logger.error(f"Invalid OpenRouter API key format: {key[:10]}...")
        return ""
        
    return key


async def get_agentql_api_key_async() -> str:
    """Get AgentQL API key from system config"""
    value = await get_system_config_async('agentql_api_key')
    if not value:
        raise Exception('AgentQL API key not configured')
    return value

def get_agentql_api_key() -> str:
    """Sync version of get_agentql_api_key"""
    value = get_system_config('agentql_api_key')
    if not value:
        raise Exception('AgentQL API key not configured')
    return value
