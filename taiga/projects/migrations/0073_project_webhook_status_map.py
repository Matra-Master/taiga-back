# -*- coding: utf-8 -*-
from django.db import migrations

import taiga.base.db.models.fields


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0072_projecttemplate_is_changelog_activated'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='webhook_status_map',
            field=taiga.base.db.models.fields.JSONField(blank=True, null=True,
                                                         verbose_name='webhook status transitions'),
        ),
    ]
