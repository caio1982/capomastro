# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('jenkins', '0001_initial'),
        ('projects', '0001_initial'),
        ('credentials', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Archive',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64)),
                ('host', models.CharField(max_length=64, null=True, blank=True)),
                ('policy', models.CharField(default=b'default', max_length=64, choices=[(b'default', b'default'), (b'cdimage', b'cdimage')])),
                ('basedir', models.CharField(max_length=128)),
                ('username', models.CharField(max_length=64, null=True, blank=True)),
                ('transport', models.CharField(max_length=64, choices=[(b'local', b'local'), (b'ssh', b'ssh')])),
                ('default', models.BooleanField(default=False)),
                ('base_url', models.CharField(default=b'', max_length=200, blank=True)),
                ('ssh_credentials', models.ForeignKey(blank=True, to='credentials.SshKeyPair', null=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ArchiveArtifact',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('archived_at', models.DateTimeField(null=True, blank=True)),
                ('archived_path', models.CharField(max_length=255, null=True, blank=True)),
                ('archived_size', models.IntegerField(default=0)),
                ('archive', models.ForeignKey(related_name=b'items', to='archives.Archive')),
                ('artifact', models.ForeignKey(to='jenkins.Artifact')),
                ('build', models.ForeignKey(blank=True, to='jenkins.Build', null=True)),
                ('dependency', models.ForeignKey(blank=True, to='projects.Dependency', null=True)),
                ('projectbuild_dependency', models.ForeignKey(blank=True, to='projects.ProjectBuildDependency', null=True)),
            ],
            options={
                'ordering': ['archived_path'],
            },
            bases=(models.Model,),
        ),
    ]
