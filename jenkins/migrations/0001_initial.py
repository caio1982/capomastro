# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import jenkins.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Artifact',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('filename', models.CharField(max_length=255)),
                ('url', models.CharField(max_length=255)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Build',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('build_id', models.CharField(max_length=255)),
                ('number', models.IntegerField()),
                ('duration', models.IntegerField(null=True)),
                ('url', models.CharField(max_length=255)),
                ('phase', models.CharField(max_length=25)),
                ('status', models.CharField(max_length=255)),
                ('console_log', models.TextField(null=True, editable=False, blank=True)),
                ('parameters', jenkins.fields.JSONField(null=True, editable=False, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-number'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='JenkinsServer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=255)),
                ('url', models.CharField(unique=True, max_length=255)),
                ('username', models.CharField(max_length=255)),
                ('password', models.CharField(max_length=255)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='JobType',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(null=True, blank=True)),
                ('config_xml', models.TextField()),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='job',
            name='jobtype',
            field=models.ForeignKey(to='jenkins.JobType'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='job',
            name='server',
            field=models.ForeignKey(to='jenkins.JenkinsServer'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='job',
            unique_together=set([('server', 'name')]),
        ),
        migrations.AddField(
            model_name='build',
            name='job',
            field=models.ForeignKey(to='jenkins.Job'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='build',
            name='requested_by',
            field=models.ForeignKey(blank=True, editable=False, to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='artifact',
            name='build',
            field=models.ForeignKey(to='jenkins.Build'),
            preserve_default=True,
        ),
    ]
