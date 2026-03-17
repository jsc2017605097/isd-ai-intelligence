from django.views import View
from django.http import JsonResponse
from .models import JobConfig
import json

class JobConfigView(View):
    def get(self, request):
        configs = JobConfig.objects.all()
        data = [
            {
                'job_type': c.job_type,
                'enabled': c.enabled,
                'limit': c.limit,
                'round_robin_types': c.round_robin_types,
                'last_type_sent': c.last_type_sent,
                'last_source_sent': c.last_source_sent,
            }
            for c in configs
        ]
        return JsonResponse({'success': True, 'data': data})

    def post(self, request):
        data = json.loads(request.body)
        config, _ = JobConfig.objects.get_or_create(job_type=data['job_type'])
        config.enabled = data.get('enabled', config.enabled)
        config.limit = data.get('limit', config.limit)
        config.round_robin_types = data.get('round_robin_types', config.round_robin_types)
        config.save()
        return JsonResponse({'success': True})