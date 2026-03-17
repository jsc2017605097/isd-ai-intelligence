from django.urls import path
from .views import CollectDataView, ArticlesAPIView, SourcesAPIView, StatsAPIView, FetchLogListView
from .views_jobconfig import JobConfigView

app_name = 'collector'

urlpatterns = [
    path('api/collect/', CollectDataView.as_view(), name='collect_data'),
    path('api/articles/', ArticlesAPIView.as_view(), name='articles'),
    path('api/sources/', SourcesAPIView.as_view(), name='sources'),
    path('api/stats/', StatsAPIView.as_view(), name='stats'),
    path('api/jobconfig/', JobConfigView.as_view(), name='job_config'),
]