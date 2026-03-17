import asyncio
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from .models import Source, Article, FetchLog
from .fetchers import DataCollector
import json
from django.shortcuts import render

@method_decorator(csrf_exempt, name='dispatch')
class CollectDataView(View):
    """API endpoint to trigger data collection"""
    
    async def post(self, request):
        try:
            data = json.loads(request.body) if request.body else {}
            source_id = data.get('source_id')
            
            collector = DataCollector()
            
            if source_id:
                try:
                    source = Source.objects.get(id=source_id, is_active=True)
                    result = await collector.collect_from_source(source)
                    return JsonResponse({
                        'success': True,
                        'message': f'Collection completed for {source.source}',
                        'data': {
                            'source': source.source,
                            'status': result['status'],
                            'articles_count': result['articles_count'],
                            'execution_time': result['execution_time']
                        }
                    })
                except Source.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': f'Source with ID {source_id} not found or inactive'
                    }, status=404)
            else:
                results = await collector.collect_all_active_sources()
                success_count = sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'success')
                total_articles = sum(r.get('articles_count', 0) for r in results if isinstance(r, dict))
                
                return JsonResponse({
                    'success': True,
                    'message': 'Collection completed for all sources',
                    'data': {
                        'sources_processed': len(results),
                        'successful_sources': success_count,
                        'total_new_articles': total_articles
                    }
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class ArticlesAPIView(View):
    """API to get articles with filtering and pagination"""
    
    def get(self, request):
        try:
            # Get query parameters
            page = int(request.GET.get('page', 1))
            page_size = min(int(request.GET.get('page_size', 20)), 100)
            source_id = request.GET.get('source_id')
            team_id = request.GET.get('team_id')
            
            articles = Article.objects.select_related('source', 'source__team').order_by('-published_at')
            
            if source_id:
                articles = articles.filter(source_id=source_id)
                
            if team_id:
                articles = articles.filter(source__team_id=team_id)
            
            # Pagination
            paginator = Paginator(articles, page_size)
            page_obj = paginator.get_page(page)
            
            # Serialize data
            articles_data = []
            for article in page_obj:
                articles_data.append({
                    'id': article.id,
                    'title': article.title,
                    'url': article.url,
                    'source': {
                        'id': article.source.id,
                        'name': article.source.source,
                        'type': article.source.get_type_display()
                    },
                    'team': {
                        'id': article.team.id,
                        'name': article.team.name,
                        'code': article.team.code
                    } if article.team else None,
                    'content_type': article.get_content_type_display(),
                    'published_at': article.published_at.isoformat(),
                    'created_at': article.created_at.isoformat(),
                    'summary': article.summary,
                    'content': article.content,
                    'thumbnail': article.thumbnail,
                    'is_ai_processed': article.is_ai_processed,
                    'ai_type': article.ai_type,
                    'ai_content': article.ai_content
                })
            
            return JsonResponse({
                'success': True,
                'data': {
                    'articles': articles_data,
                    'total_count': paginator.count,
                    'total_pages': paginator.num_pages,
                    'current_page': page
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

class SourcesAPIView(View):
    """API to get sources information"""
    
    def get(self, request):
        try:
            sources = Source.objects.all().order_by('source')
            
            sources_data = []
            for source in sources:
                # Get latest fetch log
                latest_log = source.fetch_logs.first()
                
                sources_data.append({
                    'id': source.id,
                    'source': source.source,
                    'url': source.url,
                    'type': source.get_type_display(),
                    'content_type': source.get_content_type_display(),
                    'team': source.get_team_display(),
                    'is_active': source.is_active,
                    'fetch_interval': source.fetch_interval,
                    'last_fetched': source.last_fetched.isoformat() if source.last_fetched else None,
                    'articles_count': source.articles.count(),
                    'last_fetch_status': latest_log.get_status_display() if latest_log else None,
                    'last_fetch_articles_count': latest_log.articles_count if latest_log else 0
                })
            
            return JsonResponse({
                'success': True,
                'data': {
                    'sources': sources_data,
                    'total_count': len(sources_data)
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class FetchLogsAPIView(View):
    """API to get fetch logs with filtering and pagination"""
    
    def get(self, request):
        try:
            # Get query parameters
            page = int(request.GET.get('page', 1))
            page_size = min(int(request.GET.get('page_size', 20)), 100)
            source_id = request.GET.get('source_id')
            team_id = request.GET.get('team_id')
            status = request.GET.get('status')
            
            # Build query
            logs = FetchLog.objects.select_related('source', 'source__team').order_by('-fetched_at')
            
            if source_id:
                logs = logs.filter(source_id=source_id)
            
            if team_id:
                logs = logs.filter(source__team_id=team_id)
                
            if status:
                logs = logs.filter(status=status)
            
            # Pagination
            paginator = Paginator(logs, page_size)
            page_obj = paginator.get_page(page)
            
            # Serialize data
            logs_data = []
            for log in page_obj:
                logs_data.append({
                    'id': log.id,
                    'source': {
                        'id': log.source.id,
                        'name': log.source.source,
                        'type': log.source.get_type_display()
                    },
                    'team': {
                        'id': log.team.id,
                        'name': log.team.name,
                        'code': log.team.code
                    } if log.team else None,
                    'status': log.status,
                    'status_display': log.get_status_display(),
                    'articles_count': log.articles_count,
                    'error_message': log.error_message,
                    'execution_time': log.execution_time,
                    'fetched_at': log.fetched_at.isoformat()
                })
            
            return JsonResponse({
                'success': True,
                'data': {
                    'logs': logs_data,
                    'total_count': paginator.count,
                    'total_pages': paginator.num_pages,
                    'current_page': page
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

class AILogsAPIView(View):
    """API to get AI logs with filtering and pagination"""
    
    def get(self, request):
        try:
            # Get query parameters
            page = int(request.GET.get('page', 1))
            page_size = min(int(request.GET.get('page_size', 20)), 100)
            team_id = request.GET.get('team_id')
            status = request.GET.get('status')
            
            # Build query
            logs = AILog.objects.select_related(
                'article', 'article__source', 'article__source__team'
            ).order_by('-created_at')
            
            if team_id:
                logs = logs.filter(article__source__team_id=team_id)
                
            if status:
                logs = logs.filter(status=status)
            
            # Pagination
            paginator = Paginator(logs, page_size)
            page_obj = paginator.get_page(page)
            
            # Serialize data
            logs_data = []
            for log in page_obj:
                logs_data.append({
                    'id': log.id,
                    'url': log.url,
                    'team': {
                        'id': log.team.id,
                        'name': log.team.name,
                        'code': log.team.code
                    } if log.team else None,
                    'prompt': log.prompt,
                    'response': log.response,
                    'result': log.result,
                    'status': log.status,
                    'error_message': log.error_message,
                    'created_at': log.created_at.isoformat()
                })
            
            return JsonResponse({
                'success': True,
                'data': {
                    'logs': logs_data,
                    'total_count': paginator.count,
                    'total_pages': paginator.num_pages,
                    'current_page': page
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

class StatsAPIView(View):
    """API to get collection statistics"""
    
    def get(self, request):
        try:
            from django.db.models import Count, Q
            from datetime import datetime, timedelta
            
            # Basic stats
            total_sources = Source.objects.count()
            active_sources = Source.objects.filter(is_active=True).count()
            total_articles = Article.objects.count()
            
            # Articles by content type
            articles_by_type = Article.objects.values('content_type').annotate(
                count=Count('id')
            ).order_by('content_type')
            
            # Recent articles (last 24 hours)
            yesterday = datetime.now() - timedelta(days=1)
            recent_articles = Article.objects.filter(fetched_at__gte=yesterday).count()
            
            # Success rate from recent fetch logs (last 100 attempts)
            recent_logs = FetchLog.objects.order_by('-fetched_at')[:100]
            if recent_logs:
                successful_fetches = sum(1 for log in recent_logs if log.status == 'success')
                success_rate = (successful_fetches / len(recent_logs)) * 100
            else:
                success_rate = 0
            
            # Top sources by article count
            top_sources = Source.objects.annotate(
                article_count=Count('articles')
            ).order_by('-article_count')[:5]
            
            top_sources_data = [
                {
                    'source': source.source,
                    'article_count': source.article_count,
                    'type': source.get_type_display()
                }
                for source in top_sources
            ]
            
            return JsonResponse({
                'success': True,
                'data': {
                    'overview': {
                        'total_sources': total_sources,
                        'active_sources': active_sources,
                        'total_articles': total_articles,
                        'recent_articles_24h': recent_articles,
                        'success_rate_percent': round(success_rate, 2)
                    },
                    'articles_by_content_type': [
                        {
                            'content_type': dict(Article._meta.get_field('content_type').choices)[item['content_type']],
                            'count': item['count']
                        }
                        for item in articles_by_type
                    ],
                    'top_sources': top_sources_data
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)