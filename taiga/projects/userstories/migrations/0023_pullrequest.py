# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def migrate_data_forward(apps, schema_editor):
    OldModel = apps.get_model("userstories", "UserStoryPullRequest")
    db_alias = schema_editor.connection.alias
    for obj in OldModel.objects.using(db_alias).all():
        us = obj.user_story
        obj.project_id = us.project_id
        obj.ref = us.ref
        obj.save(using=db_alias, update_fields=["project_id", "ref"])


def migrate_data_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('userstories', '0022_userstorypullrequest'),
        ('projects', '__first__'),
    ]

    operations = [
        # Step 1: Add new columns (nullable temporarily)
        migrations.AddField(
            model_name='userstorypullrequest',
            name='project',
            field=models.ForeignKey(
                null=True,
                to='projects.Project',
                on_delete=django.db.models.deletion.CASCADE,
                verbose_name='project',
            ),
        ),
        migrations.AddField(
            model_name='userstorypullrequest',
            name='ref',
            field=models.BigIntegerField(
                null=True,
                db_index=True,
                verbose_name='ref',
            ),
        ),
        # Step 2: Migrate data from user_story FK to project+ref
        migrations.RunPython(migrate_data_forward, migrate_data_backward),
        # Step 3: Make new columns non-nullable
        migrations.AlterField(
            model_name='userstorypullrequest',
            name='project',
            field=models.ForeignKey(
                null=False,
                to='projects.Project',
                on_delete=django.db.models.deletion.CASCADE,
                verbose_name='project',
            ),
        ),
        migrations.AlterField(
            model_name='userstorypullrequest',
            name='ref',
            field=models.BigIntegerField(
                null=False,
                db_index=True,
                verbose_name='ref',
            ),
        ),
        # Step 4: Remove old user_story FK
        migrations.RemoveField(
            model_name='userstorypullrequest',
            name='user_story',
        ),
        # Step 5: Rename model
        migrations.RenameModel(
            old_name='UserStoryPullRequest',
            new_name='PullRequest',
        ),
        # Step 6: Update Meta ordering
        migrations.AlterModelOptions(
            name='pullrequest',
            options={
                'ordering': ['project', 'ref', '-merged_at'],
                'verbose_name': 'pull request',
                'verbose_name_plural': 'pull requests',
            },
        ),
    ]
