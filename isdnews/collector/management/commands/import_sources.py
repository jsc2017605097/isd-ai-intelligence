import json
from django.core.management.base import BaseCommand
from collector.models import Source

class Command(BaseCommand):
    help = 'Import sources from JSON file'

    def add_arguments(self, parser):
        parser.add_argument(
            'json_file',
            type=str,
            help='Path to JSON file containing sources data',
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing sources instead of creating new ones',
        )

    def handle(self, *args, **options):
        json_file = options['json_file']
        update_existing = options['update']
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                sources_data = json.load(f)
            
            created_count = 0
            updated_count = 0
            
            for source_data in sources_data:
                if update_existing:
                    source, created = Source.objects.update_or_create(
                        source=source_data['source'],
                        defaults=source_data
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                else:
                    source, created = Source.objects.get_or_create(
                        source=source_data['source'],
                        defaults=source_data
                    )
                    if created:
                        created_count += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'Source "{source_data["source"]}" already exists, skipping...')
                        )
            
            if update_existing and updated_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully imported {created_count} new sources and updated {updated_count} existing sources')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully imported {created_count} sources')
                )
                
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'File {json_file} not found')
            )
        except json.JSONDecodeError as e:
            self.stdout.write(
                self.style.ERROR(f'Invalid JSON format: {e}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error importing sources: {e}')
            )