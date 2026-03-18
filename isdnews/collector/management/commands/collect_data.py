import asyncio
from django.core.management.base import BaseCommand
from django.utils import timezone
from collector.fetchers import DataCollector
from collector.models import Source

class Command(BaseCommand):
    help = 'Collect data from all active sources'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-id',
            type=int,
            help='Collect from specific source ID only',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force collection regardless of fetch interval',
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting data collection...')
        
        collector = DataCollector()
        
        if options['source_id']:
            # Collect from specific source
            try:
                source = Source.objects.get(id=options['source_id'], is_active=True)
                result = asyncio.run(collector.collect_from_source(source))
                self.print_result(source.source, result)
            except Source.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Source with ID {options["source_id"]} not found or inactive')
                )
        else:
            # Collect from all sources hoc ch nhng ngun n hn thu thp
            if not options['force']:
                # Lc cc ngun n hn thu thp bng Python (tng thch SQLite)
                now = timezone.now()
                sources = Source.objects.filter(is_active=True)
                # Nu force_collect=True th lun thu thp, cn li kim tra thi gian ch
                due_sources = [
                    s for s in sources
                    if s.force_collect or s.last_fetched is None or (now - s.last_fetched).total_seconds() >= s.fetch_interval
                ]
                if not due_sources:
                    self.stdout.write(self.style.SUCCESS('No sources due for update'))
                    return
                # Gii hn s lng ngun x l ng thi  trnh qu ti
                MAX_SOURCES = 10
                limited_sources = due_sources[:MAX_SOURCES]
                async def collect_all(due_sources, collector):
                    return await asyncio.gather(*(collector.collect_from_source(s) for s in due_sources))
                results = asyncio.run(collect_all(limited_sources, collector))
            else:
                results = asyncio.run(collector.collect_all_active_sources())
            
            self.stdout.write('\n--- Collection Summary ---')
            for i, result in enumerate(results):
                if isinstance(result, dict):
                    source_name = result['source'].source
                    self.print_result(source_name, result)
        
        self.stdout.write(self.style.SUCCESS('Data collection completed'))

    def print_result(self, source_name, result):
        if result['status'] == 'success':
            self.stdout.write(
                self.style.SUCCESS(
                    f' {source_name}: {result["articles_count"]} articles in {result["execution_time"]:.2f}s'
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f' {source_name}: {result["error_message"]}'
                )
            )