from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.urls import path
from django.shortcuts import render
from django.http import HttpResponseRedirect
import subprocess
from pathlib import Path
from collector.tasks import collect_data_from_all_sources
from .models import Source, FetchLog, AILog, JobConfig, Article, SystemConfig, Team, AISettings

# Cấu hình đường dẫn cho Env
NEWS_DIR = Path(__file__).resolve().parent.parent
HUB_DIR = NEWS_DIR.parent / "isdnews-hub"
BASE_DIR = NEWS_DIR.parent

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at', 'updated_at')
    search_fields = ('name', 'code', 'description')
    list_filter = ('is_active',)
    ordering = ['name']
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Nu ang edit
            return ['code']  # Khng cho php sa code khi  to
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
        if not obj:  # Ch p dng cho form to mi
            form.base_fields['params'].initial = {
                "prompt": "hy ly cc url lin quan n [ni dung bn cn ly] sau  gi li cho ti , yu cu d liu tr v ch l 1 mng cc url, khng c sai format nh ti yu cu"
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
    short_content.short_description = 'Ni dung'

    def short_summary(self, obj):
        if obj.summary and len(obj.summary) > 100:
            return format_html('<span title="{}">{}&hellip;</span>', obj.summary, obj.summary[:100])
        return obj.summary or ''
    short_summary.short_description = 'Tm tt'

    def short_ai_content(self, obj):
        if obj.ai_content and len(obj.ai_content) > 100:
            return format_html('<span title="{}">{}&hellip;</span>', obj.ai_content, obj.ai_content[:100])
        return obj.ai_content or ''
    short_ai_content.short_description = 'Ni dung AI'

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
    
    # Thm fields  hin th trong form
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
        """Ly tn team t article thng qua URL"""
        try:
            article = Article.objects.filter(url=obj.url).first()
            if article and article.source and article.source.team:
                return article.source.team.name
        except:
            pass
        return '-'
    get_team_name.short_description = 'Team'
    get_team_name.admin_order_field = 'url'  # Cho php sp xp theo URL

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
    
    # Thm fields  hin th trong form
    fields = ('key', 'value', 'key_type', 'team', 'description', 'is_active', 'created_at', 'updated_at')
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.key == 'openrouter_api_key':
            form.base_fields['team'].disabled = True
        return form
    
    def get_masked_value(self, obj):
        """Che giu gi tr nhy cm nh API key"""
        if obj.key_type == 'api_key' and obj.value:
            return f"{obj.value[:4]}...{obj.value[-4:]}"
        elif obj.key_type == 'webhook':
            return "webhook_url (hidden)"
        return obj.value
    get_masked_value.short_description = 'Value'

def read_env(env_path):
    config = {}
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
    return config

def write_env(env_path, updates):
    if not env_path.parent.exists(): return
    lines = env_path.read_text(encoding='utf-8').splitlines() if env_path.exists() else []
    new_lines = []
    seen = set()
    for line in lines:
        if "=" not in line: 
            new_lines.append(line)
            continue
        k = line.split("=", 1)[0].strip()
        if k in updates:
            new_lines.append(f"{k}={updates[k]}")
            seen.add(k)
        else:
            new_lines.append(line)
    for k, v in updates.items():
        if k not in seen:
            new_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(new_lines), encoding='utf-8')

@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
        
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_site.admin_view(self.ai_settings_view), name="collector_aisettings_changelist")
        ]
        return custom_urls

    def ai_settings_view(self, request):
        env_news = NEWS_DIR / ".env"
        env_hub = HUB_DIR / ".env"
        
        if request.method == "POST":
            provider = request.POST.get("AI_PROVIDER", "").strip().lower()
            ai_model = request.POST.get("AI_MODEL", "").strip()
            api_key = request.POST.get("AI_API_KEY", "").strip()
            ollama_url = request.POST.get("OLLAMA_BASE_URL", "").strip()
            openai_url = request.POST.get("AI_BASE_URL", "").strip()
            
            updates = {
                "AI_PROVIDER": provider,
                "AI_MODEL": ai_model,
            }
            if provider == "ollama":
                updates["OLLAMA_BASE_URL"] = ollama_url
                updates["AI_AUTH_METHOD"] = "apikey"
            else:
                updates["AI_API_KEY"] = api_key
                updates["AI_AUTH_METHOD"] = "apikey"
                if provider == "openai" and openai_url:
                    updates["AI_BASE_URL"] = openai_url
                else:
                    updates["AI_BASE_URL"] = ""

            write_env(env_news, updates)
            hub_updates = updates.copy()
            
            # Hub keys
            hub_updates["CHAT_MODEL"] = ai_model
            hub_updates["DIGEST_MODEL"] = ai_model
            if provider == "openai":
                hub_updates["LLM_BASE_URL"] = openai_url
            else:
                hub_updates["LLM_BASE_URL"] = ""
                
            write_env(env_hub, hub_updates)
            
            import os
            for k, v in updates.items(): os.environ[k] = v
            for k, v in hub_updates.items(): os.environ[k] = v
            
            try:
                subprocess.run("pm2 restart all --update-env", shell=True, cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                messages.success(request, "Cấu hình AI đã được lưu thành công. Hệ thống PM2 đã tự động khởi động lại!")
            except Exception as e:
                messages.warning(request, f"Đã lưu file cấu hình nhưng lỗi khi restart PM2: {e}. Vui lòng chạy lệnh 'isd restart' bằng tay.")
                
            return HttpResponseRedirect(request.path)

        config = read_env(env_news)
        context = {
            **self.admin_site.each_context(request),
            "title": "Cấu hình AI Provider",
            "config": config,
            "opts": AISettings._meta,
            "has_add_permission": False,
            "has_change_permission": True,
            "has_delete_permission": False,
            "has_view_permission": True,
        }
        return render(request, "admin/ai_settings.html", context)

def get_app_list(self, request, app_label=None):
    """Ty chnh th t hin th cc model trong admin"""
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
                'AISettings': 8,
            }.get(x['object_name'], 10))
    return app_list

admin.AdminSite.get_app_list = get_app_list
