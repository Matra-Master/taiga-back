# -*- coding: utf-8 -*-
from django.db import migrations, models


def backfill_merged_status(apps, schema_editor):
    PullRequest = apps.get_model("userstories", "PullRequest")
    db_alias = schema_editor.connection.alias
    PullRequest.objects.using(db_alias).filter(
        merged_at__isnull=False
    ).update(status="merged")


def noop_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('userstories', '0023_pullrequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='pullrequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('open', 'Open'),
                    ('merged', 'Merged'),
                    ('changes_requested', 'Changes requested'),
                ],
                default='open', max_length=20, verbose_name='status',
            ),
        ),
        migrations.RunPython(backfill_merged_status, noop_backward),
    ]
