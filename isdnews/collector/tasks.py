import asyncio
import html
import json
import re
from celery import shared_task
from django.utils import timezone
from .models import Source, Article, JobConfig, Team
from .fetchers import DataCollector, call_openrouter_ai
import logging
from django.db import transaction
from asgiref.sync import sync_to_async
from django.db.models import Q

logger = logging.getLogger(__name__)

@shared_task
def collect_data_from_source(source_id, team_code=None):
    """
    Collect data for a specific Source.
    If team_code is provided, only fetch if Source.team.code matches.
    """
    try:
        # Find source, filter by team if provided:
        if team_code:
            source = Source.objects.get(id=source_id, is_active=True, team__code=team_code)
        else:
            source = Source.objects.get(id=source_id, is_active=True)
        
        collector = DataCollector()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(collector.collect_from_source(source))
            return {
                'success': True,
                'source': source.source,
                'team': source.team.code if source.team else None,
                'articles_count': result['articles_count'],
                'status': result['status']
            }
        finally:
            loop.close()
    except Source.DoesNotExist:
        return {
            'success': False,
            'error': f'Source with ID {source_id} not found or inactive for team "{team_code}"'
        }
    except Exception as e:
        logger.error(f'Celery task failed for source {source_id}: {e}')
        return {'success': False, 'error': str(e)}


@shared_task
def collect_data_from_all_sources(team_code=None):
    logger.info('[Celery Beat] Triggering task collect_data_from_all_sources (team_code=%s)', team_code)
    try:
        collector = DataCollector()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Team_code parameter is already handled in DataCollector.collect_all_active_sources
            results = loop.run_until_complete(
                collector.collect_all_active_sources(team_code=team_code)
            )
            success_count = sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'success')
            total_articles = sum(r.get('articles_count', 0) for r in results if isinstance(r, dict))
            return {
                'success': True,
                'team': team_code,
                'sources_processed': len(results),
                'successful_sources': success_count,
                'total_new_articles': total_articles
            }
        finally:
            loop.close()
    except Exception as e:
        logger.error(f'Celery task failed for all sources (team_code={team_code}): {e}')
        return {'success': False, 'error': str(e)}


@shared_task
def scheduled_collection(team_code=None):
    """
    Cron-like task: runs periodically, checks which Sources are due (based on fetch_interval)
    If team_code is provided, only check Sources belonging to that team.
    """
    try:
        now = timezone.now()

        # Filter sources to fetch: is_active=True, and (last_fetched is NULL or fetch_interval over),
        # plus team condition if team_code is provided.
        base_qs = Source.objects.filter(is_active=True)
        if team_code:
            base_qs = base_qs.filter(team__code=team_code)

        # extra condition for time calculation
        sources_due = base_qs.extra(
            where=['last_fetched IS NULL OR (EXTRACT(EPOCH FROM %s) - EXTRACT(EPOCH FROM last_fetched)) >= fetch_interval'],
            params=[now]
        )

        if not sources_due.exists():
            return {
                'success': True,
                'message': f'No sources due for update (team_code={team_code})',
                'sources_processed': 0
            }

        results = []
        for source in sources_due:
            # Pass team_code when delaying, for later filtering in collect_data_from_source.
            results.append(
                collect_data_from_source.delay(source.id, team_code)
            )

        return {
            'success': True,
            'message': f'Triggered collection for {len(results)} sources (team_code={team_code})',
            'sources_processed': len(results)
        }
    except Exception as e:
        logger.error(f'Scheduled collection task failed (team_code={team_code}): {e}')
        return {'success': False, 'error': str(e)}


def update_article_and_config_sync(article_id, ai_content, ai_type, config_id):
    try:
        with transaction.atomic():
            article_obj = Article.objects.select_for_update().get(id=article_id)
            article_obj.ai_content = ai_content
            article_obj.is_ai_processed = True
            article_obj.ai_type = ai_type
            article_obj.save()

            config_obj = JobConfig.objects.select_for_update().get(id=config_id)
            config_obj.last_type_sent = ai_type
            config_obj.save()
            return True
    except Exception as e:
        logger.error(f"Error updating article and config: {e}")
        return False

def sanitize_json_content(content):
    """
    Sanitize content to avoid JSON parsing errors in Teams
    """
    if not content:
        return content
    
    # Escape special JSON characters
    content = str(content)
    
    # Escape backslashes first
    content = content.replace('\\', '\\\\')
    
    # Escape quotes
    content = content.replace('"', '\\"')
    
    # Escape newlines v tabs
    content = content.replace('\n', '\\n')
    content = content.replace('\r', '\\r')
    content = content.replace('\t', '\\t')
    
    # Loi b cc k t control characters
    content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', content)
    
    # Escape HTML entities if any
    content = html.escape(content, quote=False)
    
    return content

def validate_json_structure(data):
    """
    Check and fix JSON structure
    """
    try:
        # Th parse  kim tra tnh hp l
        json.dumps(data)
        return True
    except (TypeError, ValueError) as e:
        logger.error(f"JSON validation error: {e}")
        return False

@shared_task
def process_openrouter_job(team_code=None):
    logger.info('[Celery Beat] Triggering task process_openrouter_job (team_code=%s)', team_code)
    try:
        # Kim tra job config
        config = JobConfig.objects.filter(job_type='openrouter').first()
        if not config or not config.enabled:
            logger.info("OpenRouter job is disabled")
            return {'success': True, 'result': None}

        # Only process articles from active sources, not yet AI processed, and not claimed by another worker.
        base_query = Article.objects.filter(
            is_ai_processed=False,
            is_ai_processing=False,
            source__is_active=True
        )
        if team_code:
            base_query = base_query.filter(source__team__code=team_code)

        source_ids = list(
            base_query.order_by('source_id').values_list('source_id', flat=True).distinct()
        )

        if not source_ids:
            logger.info(f"No article to process (team_code={team_code})")
            return {'success': True, 'result': None}

        # Round-robin by source id
        selected_source_id = None
        if config.last_source_sent is not None:
            for sid in source_ids:
                if sid > config.last_source_sent:
                    selected_source_id = sid
                    break
        if selected_source_id is None:
            selected_source_id = source_ids[0]

        # Create list of sources in RR order (current source first, then wrap around)
        start_idx = source_ids.index(selected_source_id)
        rr_source_ids = source_ids[start_idx:] + source_ids[:start_idx]

        article = None
        claimed_source_id = None

        # Claim 1 article in RR order to avoid duplicate processing when multiple workers/tasks run concurrently.
        for sid in rr_source_ids:
            with transaction.atomic():
                candidate = (
                    Article.objects.select_for_update(skip_locked=True)
                    .filter(
                        source_id=sid,
                        is_ai_processed=False,
                        is_ai_processing=False,
                        source__is_active=True,
                    )
                    .order_by('-published_at', '-created_at', '-id')
                    .first()
                )

                if not candidate:
                    continue

                candidate.is_ai_processing = True
                candidate.save(update_fields=['is_ai_processing'])
                article = candidate
                claimed_source_id = sid
                break

        if not article:
            logger.info(f"No claimable article found (team_code={team_code})")
            return {'success': True, 'result': None}

        # Get actual team code from article.source.team
        real_team_code = None
        if article.source and article.source.team:
            real_team_code = article.source.team.code
        logger.info(f"Step 3: Team code = {real_team_code}, source_id={claimed_source_id}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Call AI (this will automatically notify Telegram if configured)
            logger.info("Step 4: Calling call_openrouter_ai")
            ai_content = loop.run_until_complete(
                call_openrouter_ai(article.content, article.url, ai_type=real_team_code)
            )
            logger.info("Step 5: AI processing and notification completed")

        except Exception as e:
            # Unlock if AI call fails so it can be retried later.
            try:
                Article.objects.filter(id=article.id).update(is_ai_processing=False)
            except Exception as release_err:
                logger.error(f"Error releasing AI processing lock: {release_err}")
            logger.error(f"Error in async operations: {e}")
            raise
        finally:
            try:
                loop.close()
            except Exception as e:
                logger.error(f"Error closing event loop: {e}")

        # Update article and RR source pointer
        logger.info("Step 6: Updating article and config")
        try:
            with transaction.atomic():
                article_obj = Article.objects.select_for_update().get(id=article.id)

                # If AI fails/fallbacks, DO NOT mark as processed
                if (not ai_content) or str(ai_content).startswith("AI_PROCESSING_ERROR:") or str(ai_content).strip() == (article_obj.content or '').strip():
                    article_obj.is_ai_processing = False
                    article_obj.save(update_fields=['is_ai_processing'])

                    config_obj = JobConfig.objects.select_for_update().get(id=config.id)
                    config_obj.last_source_sent = claimed_source_id
                    config_obj.save(update_fields=['last_source_sent'])

                    logger.warning(f"Skip marking AI processed for article {article_obj.id} due to invalid AI output")
                    return {'success': False, 'error': 'Invalid AI output; article left unprocessed'}

                article_obj.ai_content = ai_content
                article_obj.is_ai_processed = True
                article_obj.is_ai_processing = False
                article_obj.ai_type = real_team_code

                # Normalize display title: prioritize the first bullet point in AI content (Vietnamese)
                try:
                    title_candidate = None
                    for ln in (ai_content or '').split('\n'):
                        ln = ln.strip()
                        if ln.startswith('- ') and len(ln) >= 28:
                            title_candidate = ln[2:].strip().rstrip(' .;:')
                            break
                    if title_candidate:
                        normalized_title = f"Interview: {title_candidate}"
                        article_obj.title = normalized_title[:140]
                except Exception:
                    pass

                article_obj.save()

                config_obj = JobConfig.objects.select_for_update().get(id=config.id)
                config_obj.last_type_sent = real_team_code
                config_obj.last_source_sent = claimed_source_id
                config_obj.save()
        except Exception as e:
            logger.error(f"Error updating article and config: {e}")
            try:
                Article.objects.filter(id=article.id).update(is_ai_processing=False)
            except Exception as release_err:
                logger.error(f"Error releasing AI processing lock after update failure: {release_err}")
            return {'success': False, 'error': str(e)}

        logger.info("Step 7: Finished processing")
        return {'success': True, 'result': True}

    except Exception as e:
        logger.error(f"Celery task failed for OpenRouter job: {e}")
        return {'success': False, 'error': str(e)}
    