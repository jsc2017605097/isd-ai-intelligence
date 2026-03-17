# Hướng dẫn sử dụng ISD News Collector

## Cài đặt và thiết lập

### 1. Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### 2. Chạy migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Tạo superuser
```bash
python manage.py createsuperuser
```

### 4. Import nguồn dữ liệu mẫu
```bash
python manage.py import_sources sample_sources.json
```

### 5. Cấu hình AI model (Ollama/OpenRouter)
Mặc định hệ thống dùng **Qwen3 local qua Ollama** để tránh phụ thuộc model OpenRouter có thể bị gỡ.

Thêm vào `.env`:
```env
AI_PROVIDER=ollama
AI_MODEL=ollama/qwen3:30b-a3b
OLLAMA_BASE_URL=http://127.0.0.1:11434
AI_KNOWLEDGE_LEVEL=beginner
```

Tuỳ chọn:
- Dùng model local khác: đổi `AI_MODEL` (ví dụ `ollama/qwen2.5:14b`)
- Nếu muốn quay lại OpenRouter:
  - `AI_PROVIDER=openrouter`
  - `AI_MODEL=<openrouter-model-id>`
  - đảm bảo có `openrouter_api_key` trong SystemConfig

## Cấu hình nguồn dữ liệu

### Trong Django Admin (/admin/)

1. **Truy cập Sources** để quản lý nguồn dữ liệu
2. **Các loại nguồn hỗ trợ:**
   - **RSS Feed**: URL RSS/Atom feed
   - **API Endpoint**: REST API endpoint
   - **Web Tĩnh**: Sử dụng AgentQL để scrape website

### Cấu hình tham số (params field)

#### RSS Feed
```json
{}
```
*Không cần tham số đặc biệt*

#### API Endpoint
```json
{
  "headers": {
    "Authorization": "Bearer your_token",
    "User-Agent": "ISDNews/1.0"
  },
  "query_params": {
    "category": "technology",
    "limit": 50
  }
}
```

#### Web Tĩnh (AgentQL)
```json
{
  "api_key": "your_agentql_api_key",
  "prompt": "Lấy tất cả các URL tin tức về kinh tế, trả về dưới dạng mảng"
}
```

## Thu thập dữ liệu

### 1. Sử dụng Management Commands

#### Thu thập từ tất cả nguồn
```bash
python manage.py collect_data
```

#### Thu thập từ nguồn cụ thể
```bash
python manage.py collect_data --source-id 1
```

#### Bắt buộc thu thập (bỏ qua thời gian chờ)
```bash
python manage.py collect_data --force
```

### 2. Sử dụng API

#### Trigger collection
```bash
# Thu thập tất cả
curl -X POST http://localhost:8000/collector/api/collect/

# Thu thập nguồn cụ thể
curl -X POST http://localhost:8000/collector/api/collect/ \
  -H "Content-Type: application/json" \
  -d '{"source_id": 1}'
```

#### Lấy danh sách bài viết
```bash
# Tất cả bài viết
curl http://localhost:8000/collector/api/articles/

# Với pagination
curl "http://localhost:8000/collector/api/articles/?page=1&page_size=10"

# Lọc theo nguồn
curl "http://localhost:8000/collector/api/articles/?source_id=1"

# Lọc theo loại nội dung
curl "http://localhost:8000/collector/api/articles/?content_type=1"
```

#### Xem thống kê
```bash
curl http://localhost:8000/collector/api/stats/
```

## Celery Background Tasks (Optional)

### 1. Cài đặt Redis/RabbitMQ
```bash
# Ubuntu/Debian
sudo apt-get install redis-server

# macOS
brew install redis
```

### 2. Cấu hình Celery trong settings.py
```python
# Celery Configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Periodic tasks
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'scheduled-collection': {
        'task': 'collector.tasks.scheduled_collection',
        'schedule': crontab(minute=0, hour='*/2'),  # Every 2 hours
    },
}
```
source venv/bin/activate
### 3. Chạy Celery
```bash
# Terminal 1: Celery Worker
celery -A isdnews worker --loglevel=info --detach --logfile=./logs/celery_worker.log

#use on window
celery -A isdnews worker -l info -P solo 
# Terminal 2: Celery Beat (cho periodic tasks)
celery -A isdnews beat -l info --detach --logfile=./logs/celery_beat.log
celery -A isdnews beat --loglevel=info
```
<!-- static production -->
python manage.py collectstatic --noinput
## Monitoring và Logs

### 1. Xem logs thu thập
- Trong Django Admin: **Fetch Logs**
- Hoặc qua API: `/collector/api/stats/`

### 2. Monitoring sources
- **Sources** trong admin panel
- API endpoint: `/collector/api/sources/`

### 3. Database queries cho phân tích
```python
from collector.models import Source, Article, FetchLog

# Top sources theo số lượng bài viết
top_sources = Source.objects.annotate(
    article_count=Count('articles')
).order_by('-article_count')

# Success rate trong 24h qua
from datetime import datetime, timedelta
yesterday = datetime.now() - timedelta(days=1)
recent_logs = FetchLog.objects.filter(fetched_at__gte=yesterday)
success_rate = recent_logs.filter(status='success').count() / recent_logs.count() * 100
```

## Mở rộng hệ thống

### 1. Thêm loại fetcher mới
```python
# collector/fetchers.py
class CustomFetcher(BaseFetcher):
    async def fetch(self) -> List[Dict[str, Any]]:
        # Implement your custom logic
        pass

# Thêm vào FetcherFactory
FetcherFactory.FETCHER_MAP['custom'] = CustomFetcher
```

### 2. Tùy chỉnh parser cho API
```python
def _parse_api_response(self, data: Dict) -> List[Dict[str, Any]]:
    # Customize based on your API structure
    pass
```

### 3. Thêm fields cho Article model
```python
# collector/models.py
class Article(models.Model):
    # ... existing fields
    custom_field = models.CharField(max_length=255, blank=True)
```

## Troubleshooting

### 1. Lỗi import asyncio
- Đảm bảo Python >= 3.7
- Kiểm tra cài đặt aiohttp

### 2. AgentQL không hoạt động
- Kiểm tra API key trong params
- Verify quota và permissions

### 3. RSS parsing lỗi
- Kiểm tra URL RSS có hợp lệ
- Test với feedparser trực tiếp

### 4. Performance issues
- Tăng fetch_interval cho các nguồn ít quan trọng
- Sử dụng Celery cho background processing
- Cân nhắc database indexing
