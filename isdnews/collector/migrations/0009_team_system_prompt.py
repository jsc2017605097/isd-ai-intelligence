from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('collector', '0008_article_is_ai_processing_jobconfig_last_source_sent'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='system_prompt',
            field=models.TextField(blank=True, help_text='Custom System Prompt for this team', null=True),
        ),
    ]
