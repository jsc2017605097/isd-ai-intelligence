from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from collector.tasks import collect_data_from_all_sources
from .models import Source, FetchLog, AILog, JobConfig, Article, SystemConfig, Team

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at', 'updated_at')
    search_fields = ('name', 'code', 'description')
    list_filter = ('is_active',)
    ordering = ['name']
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Nếu đang edit
            return ['code']  # Không cho phép sửa code khi đã tạo
        return []

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    class Media:
        css = {'all': ('admin/css/custom.css',)}

    list_display = ('source', 'url', 'type', 'team', 'is_active', 'fetch_interval', 'force_collect')
    search_fields = ('source', 'url')
    list_filter = ('type', 'team', 'is_active', 'force_collect')
    ordering = ['source']
    
    actions = ['run_collect_all_job']
    def run_collect_all_job(self, request, queryset):
        collect_data_from_all_sources.delay()
        self.message_user(request, "Data collection job has been queued!", messages.SUCCESS)
    run_collect_all_job.short_description = "Run Data Collection (Celery)"
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not obj:  # Chỉ áp dụng cho form tạo mới
            form.base_fields['params'].initial = {
                "prompt": "hãy lấy các url liên quan đến [nội dung bạn cần lấy] sau đó gửi lại cho tôi , yêu cầu dữ liệu trả về chỉ là 1 mảng các url, không được sai format như tôi yêu cầu"
            }
        return form

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "type":
            field.widget.attrs['onchange'] = 'handleTypeChange(this);'
        return field

    class Meta:
        model = Source
        app_label = "Data Source Management"

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    class Media:
        css = {'all': ('admin/css/custom.css',)}

    list_display = ('title', 'source', 'team_name', 'published_at', 
                   'short_summary', 'short_content', 'short_ai_content', 'is_ai_processed')
    list_filter = ('source', 'source__team', 'is_ai_processed', 'published_at')
    search_fields = ('title', 'content', 'summary', 'ai_content')
    date_hierarchy = 'published_at'
    ordering = ('-published_at',)
    
    fields = ('title', 'url', 'source', 'published_at', 
             'summary', 'content', 'thumbnail', 'is_ai_processed', 
             'ai_type', 'ai_content', 'created_at')
    readonly_fields = ('created_at',)

    def short_content(self, obj):
        if obj.content and len(obj.content) > 100:
            return format_html('<span title="{}">{}&hellip;</span>', obj.content, obj.content[:100])
        return obj.content or ''
    short_content.short_description = 'Nội dung'

    def short_summary(self, obj):
        if obj.summary and len(obj.summary) > 100:
            return format_html('<span title="{}">{}&hellip;</span>', obj.summary, obj.summary[:100])
        return obj.summary or ''
    short_summary.short_description = 'Tóm tắt'

    def short_ai_content(self, obj):
        if obj.ai_content and len(obj.ai_content) > 100:
            return format_html('<span title="{}">{}&hellip;</span>', obj.ai_content, obj.ai_content[:100])
        return obj.ai_content or ''
    short_ai_content.short_description = 'Nội dung AI'

    def team_name(self, obj):
        return obj.team_name
    team_name.short_description = 'Team'
    team_name.admin_order_field = 'source__team__name'

@admin.register(FetchLog)
class FetchLogAdmin(admin.ModelAdmin):
    list_display = ('fetched_at', 'source', 'team_name', 'status', 'articles_count', 
                   'execution_time', 'error_message')
    list_filter = ('status', 'source', 'source__team', 'fetched_at')
    search_fields = ('error_message', 'source__source')
    date_hierarchy = 'fetched_at'
    readonly_fields = [f.name for f in FetchLog._meta.fields]
    
    def team_name(self, obj):
        return obj.team_name
    team_name.short_description = 'Team'
    team_name.admin_order_field = 'source__team__name'

@admin.register(AILog)
class AILogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'url', 'get_team_name', 'status', 'error_message', 
                   'short_prompt', 'short_result')
    search_fields = ('url', 'prompt', 'result', 'error_message')
    list_filter = ('status', 'created_at')
    readonly_fields = [f.name for f in AILog._meta.fields]
    date_hierarchy = 'created_at'
    
    # Thêm fields để hiển thị trong form
    fields = ('url', 'prompt', 'response', 'result', 'status', 
             'error_message', 'created_at')

    def short_prompt(self, obj):
        if len(obj.prompt) > 100:
            return format_html('<span title="{}">{}&hellip;</span>', obj.prompt, obj.prompt[:100])
        return obj.prompt
    short_prompt.short_description = 'Prompt'

    def short_result(self, obj):
        if len(obj.result) > 100:
            return format_html('<span title="{}">{}&hellip;</span>', obj.result, obj.result[:100])
        return obj.result
    short_result.short_description = 'Result'
    
    def get_team_name(self, obj):
        """Lấy tên team từ article thông qua URL"""
        try:
            article = Article.objects.filter(url=obj.url).first()
            if article and article.source and article.source.team:
                return article.source.team.name
        except:
            pass
        return '-'
    get_team_name.short_description = 'Team'
    get_team_name.admin_order_field = 'url'  # Cho phép sắp xếp theo URL

@admin.register(JobConfig)
class JobConfigAdmin(admin.ModelAdmin):
    list_display = ['job_type', 'enabled', 'limit', 'round_robin_types', 'last_type_sent', 'last_source_sent']
    list_editable = ['enabled']
    search_fields = ['job_type']
    list_filter = ['enabled', 'job_type']

    def get_fields(self, request, obj=None):
        fields = ['job_type', 'enabled', 'round_robin_types', 'last_type_sent', 'last_source_sent']
        if not obj or obj.job_type == 'crawl':
            fields.insert(2, 'limit')
        return fields

    def get_readonly_fields(self, request, obj=None):
        return ['last_type_sent', 'last_source_sent']

@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ('key', 'team', 'get_masked_value', 'is_active', 'updated_at')
    list_filter = ('key', 'team', 'is_active')
    search_fields = ('key', 'description', 'value')
    readonly_fields = ('created_at', 'updated_at', 'key_type')
    
    # Thêm fields để hiển thị trong form
    fields = ('key', 'value', 'key_type', 'team', 'description', 'is_active', 'created_at', 'updated_at')
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.key == 'openrouter_api_key':
            form.base_fields['team'].disabled = True
        return form
    
    def get_masked_value(self, obj):
        """Che giấu giá trị nhạy cảm như API key"""
        if obj.key_type == 'api_key' and obj.value:
            return f"{obj.value[:4]}...{obj.value[-4:]}"
        elif obj.key_type == 'webhook':
            return "webhook_url (hidden)"
        return obj.value
    get_masked_value.short_description = 'Value'

def get_app_list(self, request, app_label=None):
    """Tùy chỉnh thứ tự hiển thị các model trong admin"""
    app_dict = self._build_app_dict(request, app_label)
    app_list = sorted(app_dict.values(), key=lambda x: x['name'].lower())

    for app in app_list:
        if app['app_label'] == 'collector':
            app['models'].sort(key=lambda x: {
                'Team': 1,
                'Source': 2,
                'Article': 3,
                'FetchLog': 4,
                'AILog': 5,
                'JobConfig': 6,
                'SystemConfig': 7,
            }.get(x['object_name'], 10))
    return app_list

admin.AdminSite.get_app_list = get_app_list
