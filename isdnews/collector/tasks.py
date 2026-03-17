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
    Thu thập dữ liệu cho một Source cụ thể.
    Nếu team_code != None, sẽ chỉ fetch nếu Source.team.code == team_code.
    """
    try:
        # Tìm source, thêm điều kiện lọc team nếu có:
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
    logger.info('[Celery Beat] Đã gọi task collect_data_from_all_sources (team_code=%s)', team_code)
    try:
        collector = DataCollector()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Trong DataCollector.collect_all_active_sources, bạn đã có tham số team_code
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
    Task gần giống cron: chạy định kỳ, kiểm tra những Source nào “due” (dựa vào fetch_interval)
    Nếu có team_code, chỉ check những Source.belongs_to team đó.
    """
    try:
        now = timezone.now()

        # Lọc những Source cần fetch: is_active=True, và (last_fetched là NULL hoặc đã quá fetch_interval),
        # thêm điều kiện team nếu team_code được truyền vào.
        base_qs = Source.objects.filter(is_active=True)
        if team_code:
            base_qs = base_qs.filter(team__code=team_code)

        # extra để tính điều kiện về thời gian
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
            # Truyền team_code khi delay, để collect_data_from_source lọc thêm.
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
    Làm sạch nội dung để tránh lỗi JSON parsing trong Teams
    """
    if not content:
        return content
    
    # Escape các ký tự đặc biệt JSON
    content = str(content)
    
    # Escape backslashes trước
    content = content.replace('\\', '\\\\')
    
    # Escape quotes
    content = content.replace('"', '\\"')
    
    # Escape newlines và tabs
    content = content.replace('\n', '\\n')
    content = content.replace('\r', '\\r')
    content = content.replace('\t', '\\t')
    
    # Loại bỏ các ký tự control characters
    content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', content)
    
    # Escape HTML entities nếu có
    content = html.escape(content, quote=False)
    
    return content

def validate_json_structure(data):
    """
    Kiểm tra và sửa cấu trúc JSON
    """
    try:
        # Thử parse để kiểm tra tính hợp lệ
        json.dumps(data)
        return True
    except (TypeError, ValueError) as e:
        logger.error(f"JSON validation error: {e}")
        return False

@shared_task
def process_openrouter_job(team_code=None):
    logger.info('[Celery Beat] Đã gọi task process_openrouter_job (team_code=%s)', team_code)
    try:
        # Kiểm tra job config
        config = JobConfig.objects.filter(job_type='openrouter').first()
        if not config or not config.enabled:
            logger.info("OpenRouter job is disabled")
            return {'success': True, 'result': None}

        # Chỉ xử lý article từ source active, chưa xử lý AI và chưa bị claim bởi worker khác.
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

        # Round-robin theo source id
        selected_source_id = None
        if config.last_source_sent is not None:
            for sid in source_ids:
                if sid > config.last_source_sent:
                    selected_source_id = sid
                    break
        if selected_source_id is None:
            selected_source_id = source_ids[0]

        # Tạo danh sách thử theo thứ tự RR (source hiện tại trước, sau đó quay vòng)
        start_idx = source_ids.index(selected_source_id)
        rr_source_ids = source_ids[start_idx:] + source_ids[:start_idx]

        article = None
        claimed_source_id = None

        # Claim 1 bài theo thứ tự RR, tránh xử lý trùng khi có nhiều worker/task chạy đồng thời.
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

        # Lấy team code thực tế từ article.source.team
        real_team_code = None
        if article.source and article.source.team:
            real_team_code = article.source.team.code
        logger.info(f"Step 3: Team code = {real_team_code}, source_id={claimed_source_id}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Gọi AI (hàm này sẽ tự động gửi thông báo Telegram nếu có cấu hình)
            logger.info("Step 4: Gọi call_openrouter_ai")
            ai_content = loop.run_until_complete(
                call_openrouter_ai(article.content, article.url, ai_type=real_team_code)
            )
            logger.info("Step 5: Đã hoàn thành xử lý AI và gửi thông báo")

        except Exception as e:
            # Nhả claim nếu gọi AI lỗi để lần sau có thể retry.
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

        # Cập nhật bài viết và con trỏ RR source
        logger.info("Step 6: Cập nhật bài viết và config")
        try:
            with transaction.atomic():
                article_obj = Article.objects.select_for_update().get(id=article.id)

                # Nếu AI lỗi/fallback thì KHÔNG đánh dấu đã xử lý
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

                # Chuẩn hoá tiêu đề hiển thị: ưu tiên bullet đầu tiên trong AI content (tiếng Việt)
                try:
                    title_candidate = None
                    for ln in (ai_content or '').split('\n'):
                        ln = ln.strip()
                        if ln.startswith('- ') and len(ln) >= 28:
                            title_candidate = ln[2:].strip().rstrip(' .;:')
                            break
                    if title_candidate:
                        normalized_title = f"Phỏng vấn: {title_candidate}"
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

        logger.info("Step 7: Hoàn thành xử lý")
        return {'success': True, 'result': True}

    except Exception as e:
        logger.error(f"Celery task failed for OpenRouter job: {e}")
        return {'success': False, 'error': str(e)}
    