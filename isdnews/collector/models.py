from django.contrib.auth.models import User
from django.db import models
from django.core.exceptions import ValidationError
import json
from django.utils import timezone

class Team(models.Model):
    """Model qun l cc team trong h thng"""
    code = models.CharField(max_length=20, unique=True, help_text="M code ca team (v d: dev, ba, system)")
    name = models.CharField(max_length=100, help_text="Tn y  ca team")
    description = models.TextField(blank=True, help_text="M t v team")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Team"
        verbose_name_plural = "Teams"
        ordering = ['name']
        app_label = 'collector'

class Source(models.Model):
    TYPE_CHOICES = [
        ('api', 'API Endpoint'),
        ('rss', 'RSS Feed'),
        ('static', 'Web Tnh (AgentQL)'),
    ]

    url = models.URLField()
    source = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name='sources')
    params = models.JSONField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Thng tin v cu hnh thu thp
    fetch_interval = models.IntegerField(default=3600, help_text="Interval in seconds")
    last_fetched = models.DateTimeField(null=True, blank=True)
    force_collect = models.BooleanField(default=False, help_text="Bt  lun thu thp ngun ny, b qua thi gian ch")
    
    def clean(self):
        super().clean()
        
        # Set default params for static type
        if self.type == 'static':
            if not self.params:
                self.params = {
                    "prompt": "hy ly cc url lin quan n [ni dung bn cn ly] sau  gi li cho ti , yu cu d liu tr v ch l 1 mng cc url, khng c sai format nh ti yu cu"
                }
            elif 'prompt' not in self.params:
                self.params['prompt'] = "hy ly cc url lin quan n [ni dung bn cn ly] sau  gi li cho ti , yu cu d liu tr v ch l 1 mng cc url, khng c sai format nh ti yu cu"
        
        # Validate params structure
        if self.params:
            try:
                if self.type == 'api' and 'headers' in self.params:
                    if not isinstance(self.params['headers'], dict):
                        raise ValidationError({'params': 'API headers must be a dictionary'})
                elif self.type == 'static' and 'prompt' not in self.params:
                    raise ValidationError({'params': 'Static sources must have a prompt parameter'})
            except (TypeError, KeyError) as e:
                raise ValidationError({'params': f'Invalid params structure: {e}'})

    def __str__(self):
        return f"{self.source} ({self.get_type_display()})"

    class Meta:
        verbose_name = "Data Source"
        verbose_name_plural = "Data Sources"
        ordering = ['source']
        app_label = 'collector'

class Article(models.Model):
    """Model  lu tr cc bi vit  thu thp"""
    title = models.CharField(max_length=500)
    url = models.URLField(unique=True)
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name='articles')
    published_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
    summary = models.TextField(blank=True)
    content = models.TextField(blank=True)
    thumbnail = models.URLField(blank=True)
    is_ai_processed = models.BooleanField(default=False)
    is_ai_processing = models.BooleanField(default=False)
    ai_type = models.CharField(max_length=10, blank=True)
    ai_content = models.TextField(blank=True)
    
    @property
    def team(self):
        """Ly thng tin team t source"""
        return self.source.team
    
    @property
    def team_name(self):
        """Ly tn team t source"""
        return self.source.team.name if self.source.team else None
    
    class Meta:
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        ordering = ['-published_at']
        app_label = 'collector'
    
    def __str__(self):
        return self.title

class FetchLog(models.Model):
    """Log vic thu thp d liu"""
    STATUS_CHOICES = [
        ('success', 'Thnh cng'),
        ('error', 'Li'),
        ('partial', 'Mt phn'),
    ]
    
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name='fetch_logs')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    articles_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    execution_time = models.FloatField(help_text="Time in seconds")
    fetched_at = models.DateTimeField(auto_now_add=True)
    
    @property
    def team(self):
        """Ly thng tin team t source"""
        return self.source.team
    
    @property
    def team_name(self):
        """Ly tn team t source"""
        return self.source.team.name if self.source.team else None
    
    class Meta:
        verbose_name = "Fetch Log"
        verbose_name_plural = "Fetch Logs"
        ordering = ['-fetched_at']
    
    def __str__(self):
        return f"{self.source.source} - {self.get_status_display()} ({self.fetched_at})"

class AILog(models.Model):
    """Log tng tc vi OpenRouter AI"""
    url = models.URLField()
    prompt = models.TextField()
    response = models.TextField(blank=True)
    result = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[('success', 'Thnh cng'), ('error', 'Li')], default='success')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    @property
    def team(self):
        """Ly thng tin team t article thng qua URL"""
        try:
            article = Article.objects.filter(url=self.url).first()
            if article and article.source and article.source.team:
                return article.source.team
        except:
            pass
        return None
    
    @property
    def team_name(self):
        """Ly tn team t article nu c"""
        if self.team:
            return self.team.name
        return None

    class Meta:
        verbose_name = "Log AI (OpenRouter)"
        verbose_name_plural = "Log AI (OpenRouter)"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.url} - {self.status} ({self.created_at})"

class JobConfig(models.Model):
    JOB_TYPE_CHOICES = [
        ('crawl', 'Co d liu'),
        ('openrouter', 'Gi OpenRouter'),
    ]
    job_type = models.CharField(max_length=50, choices=JOB_TYPE_CHOICES, unique=True)
    enabled = models.BooleanField(default=True)
    limit = models.IntegerField(default=10)
    round_robin_types = models.JSONField(default=list, blank=True)  # ['dev', 'ba', 'system']
    last_type_sent = models.CharField(max_length=20, blank=True, default='')
    last_source_sent = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_job_type_display()} (limit: {self.limit})"

    class Meta:
        verbose_name = "Job Config"
        verbose_name_plural = "Job Configs"
        app_label = "collector"


class SystemConfig(models.Model):
    """Model lu tr cu hnh h thng"""
    KEY_CHOICES = [
        ('openrouter_api_key', 'OpenRouter API Key'),
        ('teams_webhook', 'Teams Webhook URL'),
        ('agentql_api_key', 'AgentQL API Key')
    ]

    KEY_TYPES = [
        ('api_key', 'API Key'),
        ('webhook', 'Webhook URL'),
    ]

    key = models.CharField(max_length=100, choices=KEY_CHOICES,
                         help_text="Chn loi cu hnh cn thit lp")
    value = models.TextField(help_text="Nhp gi tr cu hnh (API key hoc webhook URL)")
    key_type = models.CharField(max_length=20, choices=KEY_TYPES)
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name='configs', 
                           null=True, blank=True,
                           help_text="Chn team (ch p dng cho Teams Webhook)")
    description = models.TextField(blank=True, help_text="M t v cu hnh")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.key in ['openrouter_api_key', 'agentql_api_key']:
            self.key_type = 'api_key'
            self.team = None
        else:  # teams_webhook
            self.key_type = 'webhook'
            if not self.team:
                raise ValidationError({'team': 'Team is required for Teams Webhook'})

    def __str__(self):
        if self.team:
            return f"{self.get_key_display()} ({self.team.name})"
        return self.get_key_display()

    class Meta:
        verbose_name = "System Config"
        verbose_name_plural = "System Configs"
        ordering = ['key']
        unique_together = [('key', 'team')]  # Cho php nhiu webhook vi team khc nhau
        app_label = 'collector'
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    knowledge_level = models.CharField(
        choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')],
        default='beginner'
    )