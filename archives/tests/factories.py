from __future__ import unicode_literals

import factory

from archives.models import Archive, ArchiveArtifact
from credentials.tests.factories import SshKeyPairFactory
from jenkins.tests.factories import ArtifactFactory


class ArchiveFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Archive

    name = factory.Sequence(lambda n: "Archive %d" % n)
    host = "archive.example.com"
    policy = "cdimage"
    basedir = "/var/tmp"
    username = "testing"
    ssh_credentials = factory.SubFactory(SshKeyPairFactory)
    transport = "ssh"
    base_url = "http://example.com/projects/"


class ArchiveArtifactFactory(factory.DjangoModelFactory):
    FACTORY_FOR = ArchiveArtifact

    archive = factory.SubFactory(ArchiveFactory)
    artifact = factory.SubFactory(ArtifactFactory)
