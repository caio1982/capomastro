# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import projects.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('jenkins', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Dependency',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=255)),
                ('description', models.TextField(null=True, blank=True)),
                ('parameters', models.TextField(blank=True, null=True, validators=[projects.models.validate_parameters])),
                ('job', models.ForeignKey(to='jenkins.Job', null=True)),
            ],
            options={
                'verbose_name_plural': 'dependencies',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=255)),
                ('description', models.TextField(null=True, blank=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ProjectBuild',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('ended_at', models.DateTimeField(null=True)),
                ('status', models.CharField(default=b'UNKNOWN', max_length=10)),
                ('phase', models.CharField(default=b'UNKNOWN', max_length=25)),
                ('build_id', models.CharField(max_length=20)),
                ('archived', models.DateTimeField(null=True, blank=True)),
                ('build_key', models.CharField(default=projects.models.generate_build_key, max_length=32)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ProjectBuildDependency',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('build', models.ForeignKey(related_name=b'projectbuild_dependencies', blank=True, to='jenkins.Build', null=True)),
                ('dependency', models.ForeignKey(to='projects.Dependency')),
                ('projectbuild', models.ForeignKey(related_name=b'dependencies', to='projects.ProjectBuild')),
            ],
            options={
                'verbose_name_plural': 'project build dependencies',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ProjectDependency',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('auto_track', models.BooleanField(default=True)),
                ('current_build', models.ForeignKey(editable=False, to='jenkins.Build', null=True)),
                ('dependency', models.ForeignKey(to='projects.Dependency')),
                ('project', models.ForeignKey(to='projects.Project')),
            ],
            options={
                'verbose_name_plural': 'project dependencies',
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='projectbuild',
            name='build_dependencies',
            field=models.ManyToManyField(to='jenkins.Build', through='projects.ProjectBuildDependency'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='projectbuild',
            name='project',
            field=models.ForeignKey(to='projects.Project'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='projectbuild',
            name='requested_by',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='project',
            name='dependencies',
            field=models.ManyToManyField(to='projects.Dependency', through='projects.ProjectDependency'),
            preserve_default=True,
        ),
    ]
