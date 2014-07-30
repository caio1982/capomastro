from __future__ import unicode_literals

from io import StringIO
import os
import shutil
import tempfile

from django.test import TestCase
from django.test.utils import override_settings

import mock

from archives.tasks import (
    archive_artifact_from_jenkins, process_build_artifacts,
    link_artifact_in_archive, generate_checksums)
from archives.models import Archive, ArchiveArtifact
from archives.transports import Transport, LocalTransport
from jenkins.tests.factories import ArtifactFactory, BuildFactory
from jenkins.models import Build
from projects.helpers import build_project
from projects.tasks import process_build_dependencies
from projects.models import ProjectDependency, ProjectBuildDependency
from projects.tests.factories import DependencyFactory, ProjectFactory
from .factories import ArchiveFactory


class LoggingTransport(Transport):
    """
    Test archiver that just logs the calls the Archiver
    code makes.
    """
    def __init__(self, *args, **kwargs):
        super(LoggingTransport, self).__init__(*args, **kwargs)
        self.log = []

    def start(self):
        self.log.append("START")

    def end(self):
        self.log.append("END")

    def archive_url(self, url, path, username, password):
        self.log.append("%s -> %s %s:%s" % (url, path, username, password))
        return 0

    def generate_checksums(self, archived_artifact):
        self.log.append(
            "Checksums generated for %s" % archived_artifact)

    def link_to_current(self, path):
        self.log.append(
            "Make %s current" % path)

    def link_filename_to_filename(self, source, destination):
        self.log.append(
            "Link %s to %s" % (source, destination))


class LocalArchiveTestBase(TestCase):

    def setUp(self):
        self.basedir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.basedir)


class ArchiveArtifactFromJenkinsTaskTest(LocalArchiveTestBase):

    def test_archive_artifact_from_jenkins(self):
        """
        archive_artifact_from_jenkins should get a transport, and then call
        start, end and archive_artifact on the transport.
        the correct storage.
        """
        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir)
        dependency = DependencyFactory.create()
        build = BuildFactory.create(job=dependency.job)
        artifact = ArtifactFactory.create(
            build=build, filename="testing/testing.txt")

        items = archive.add_build(artifact.build)

        fakefile = StringIO(u"Artifact from Jenkins")
        with mock.patch("archives.transports.urllib2") as urllib2_mock:
            urllib2_mock.urlopen.return_value = fakefile
            archive_artifact_from_jenkins(items[artifact][0].pk)

        [item] = list(archive.get_archived_artifacts_for_build(build))

        filename = os.path.join(self.basedir, item.archived_path)
        self.assertEqual(file(filename).read(), "Artifact from Jenkins")
        self.assertEqual(21, item.archived_size)

    def test_archive_artifact_from_finalized_dependency_build(self):
        """
        archive_artifact_from_jenkins should get a transport, and then call
        start, end and archive_artifact on the transport.
        the correct storage.
        """
        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir)
        dependency = DependencyFactory.create()
        build = BuildFactory.create(job=dependency.job)
        artifact = ArtifactFactory.create(
            build=build, filename="testing/testing.txt")

        [item] = archive.add_build(artifact.build)[artifact]
        transport = LoggingTransport(archive)
        with mock.patch.object(
                Archive, "get_transport", return_value=transport):
            archive_artifact_from_jenkins(item.pk)

        self.assertEqual(
            ["START",
             "%s -> %s root:testing" % (artifact.url, item.archived_path),
             "Make %s current" % item.archived_path,
             "END"],
            transport.log)

    def test_archive_artifact_from_finalized_projectbuild(self):
        """
        If the build is complete, and the item being archived is in a FINALIZED
        ProjectBuild, it should use the transport to set the current directory
        correctly.
        """
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        projectbuild = build_project(project, queue_build=False)
        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key,
            phase=Build.FINALIZED)
        ProjectBuildDependency.objects.create(
            build=build, projectbuild=projectbuild, dependency=dependency)
        artifact = ArtifactFactory.create(
            build=build, filename="testing/testing.txt")

        # We need to ensure that the artifacts are all connected up.
        process_build_dependencies(build.pk)

        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir, default=True)
        item = [x for x in archive.add_build(artifact.build)[artifact]
                if x.projectbuild_dependency][0]

        transport = LoggingTransport(archive)
        with mock.patch.object(
                Archive, "get_transport", return_value=transport):
            archive_artifact_from_jenkins(item.pk)

        self.assertEqual(
            ["START",
             "%s -> %s root:testing" % (artifact.url, item.archived_path),
             "Make %s current" % item.archived_path,
             "END"],
            transport.log)

    def test_archive_artifact_from_non_finalized_projectbuild(self):
        """
        If the build is complete, and the item being archived is in a FINALIZED
        ProjectBuild, it should use the transport to set the current directory
        correctly.
        """
        project = ProjectFactory.create()
        dependency1 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency1)

        dependency2 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency2)

        projectbuild = build_project(project, queue_build=False)
        build = BuildFactory.create(
            job=dependency1.job, build_id=projectbuild.build_key,
            phase=Build.FINALIZED)
        ProjectBuildDependency.objects.create(
            build=build, projectbuild=projectbuild, dependency=dependency1)
        artifact = ArtifactFactory.create(
            build=build, filename="testing/testing.txt")

        # We need to ensure that the artifacts are all connected up.
        process_build_dependencies(build.pk)

        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir, default=True)
        item = [x for x in archive.add_build(artifact.build)[artifact]
                if x.projectbuild_dependency][0]

        transport = LoggingTransport(archive)
        with mock.patch.object(
                Archive, "get_transport", return_value=transport):
            archive_artifact_from_jenkins(item.pk)

        self.assertEqual(
            ["START",
             "%s -> %s root:testing" % (artifact.url, item.archived_path),
             "END"],
            transport.log)

    def test_archive_artifact_from_jenkins_transport_lifecycle(self):
        """
        archive_artifact_from_jenkins should get a transport, and copy the file
        to the correct storage.
        """
        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir)
        dependency = DependencyFactory.create()
        build = BuildFactory.create(job=dependency.job)
        artifact = ArtifactFactory.create(
            build=build, filename="testing/testing.txt")

        archive.add_build(artifact.build)
        [item] = list(archive.get_archived_artifacts_for_build(build))

        self.assertIsNone(item.archived_at)

        transport = LoggingTransport(archive)
        with mock.patch.object(
                Archive, "get_transport", return_value=transport):
            archive_artifact_from_jenkins(item.pk)

        [item] = list(archive.get_archived_artifacts_for_build(build))
        self.assertEqual(
            ["START",
             "%s -> %s root:testing" % (artifact.url, item.archived_path),
             "Make %s current" % item.archived_path,
             "END"],
            transport.log)
        self.assertIsNotNone(item.archived_at)


class GenerateChecksumsTaskTest(TestCase):

    def setUp(self):
        self.basedir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.basedir)

    @override_settings(CELERY_ALWAYS_EAGER=True)
    def test_generate_checksums(self):
        """
        generate_checksums should call the generate_checksums method
        on the transport from the archive with the build to generate
        the checksums for.
        """
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        projectbuild = build_project(project, queue_build=False)
        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key)
        projectbuild_dependency = ProjectBuildDependency.objects.create(
            build=build, projectbuild=projectbuild, dependency=dependency)
        artifact = ArtifactFactory.create(
            build=build, filename="testing/testing.txt")
        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir, default=True)
        archived_artifact = ArchiveArtifact.objects.create(
            build=build, archive=archive, artifact=artifact,
            archived_path="/srv/builds/200101.01/artifact_filename",
            projectbuild_dependency=projectbuild_dependency)

        transport = LoggingTransport(archive)

        with mock.patch.object(
                Archive, "get_transport", return_value=transport):
            generate_checksums(build.pk)

        self.assertEqual(
            ["START", "Checksums generated for %s" % archived_artifact, "END"],
            transport.log)


class ProcessBuildArtifactsTaskTest(TestCase):

    def setUp(self):
        self.basedir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.basedir)

    @override_settings(CELERY_ALWAYS_EAGER=True)
    def test_process_build_artifacts(self):
        """
        process_build_artifacts is chained from the Jenkins postbuild
        processing, it should arrange for the artifacts for the provided build
        to be archived in the default archive.
        """
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)

        projectbuild = build_project(project, queue_build=False)

        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key)
        ArtifactFactory.create(
            build=build, filename="testing/testing.txt")
        # We need to ensure that the artifacts are all connected up.
        process_build_dependencies(build.pk)

        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir, default=True,
            policy="cdimage")
        with mock.patch("archives.transports.urllib2") as urllib2_mock:
            urllib2_mock.urlopen.side_effect = lambda x: StringIO(
                u"Artifact from Jenkins")
            process_build_artifacts(build.pk)

        [item1, item2] = list(archive.get_archived_artifacts_for_build(build))

        filename = os.path.join(self.basedir, item1.archived_path)
        self.assertEqual(file(filename).read(), "Artifact from Jenkins")

        filename = os.path.join(self.basedir, item2.archived_path)
        self.assertEqual(file(filename).read(), "Artifact from Jenkins")

    @override_settings(CELERY_ALWAYS_EAGER=True)
    def test_process_build_artifacts_with_no_default_archive(self):
        """
        If we have no default archive, we should log the fact that we can't
        automatically archive artifacts.
        """
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)

        projectbuild = build_project(project, queue_build=False)

        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key)
        ArtifactFactory.create(
            build=build, filename="testing/testing.txt")
        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir, default=False)

        with mock.patch("archives.tasks.logging") as mock_logging:
            result = process_build_artifacts.delay(build.pk)

        # We must return the build.pk for further chained calls to work.
        self.assertEqual(build.pk, result.get())

        mock_logging.assert_has_calls([
            mock.call.info(
                "Processing build artifacts from build %s %d",
                build, build.number),
            mock.call.info(
                "No default archiver - build not automatically archived.")
        ])
        self.assertEqual(
            [],
            list(archive.get_archived_artifacts_for_build(build)))

    @override_settings(CELERY_ALWAYS_EAGER=True)
    def test_process_build_artifacts_with_multiple_artifacts(self):
        """
        All the artifacts should be individually linked.
        """
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)

        projectbuild = build_project(project, queue_build=False)

        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key)
        ArtifactFactory.create(
            build=build, filename="testing/testing1.txt")
        ArtifactFactory.create(
            build=build, filename="testing/testing2.txt")
        # We need to ensure that the artifacts are all connected up.
        process_build_dependencies(build.pk)

        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir, default=True,
            policy="cdimage")

        with mock.patch("archives.transports.urllib2") as urllib2_mock:
            urllib2_mock.urlopen.side_effect = lambda x: StringIO(
                u"Artifact %s")
            with mock.patch(
                    "archives.tasks.archive_artifact_from_jenkins"
                    ) as archive_task:
                with mock.patch(
                        "archives.tasks.link_artifact_in_archive"
                        ) as link_task:
                    process_build_artifacts(build.pk)

        [item1, item2, item3, item4] = list(
            archive.get_archived_artifacts_for_build(build).order_by(
                "artifact"))

        self.assertEqual(
            [mock.call(item4.pk), mock.call(item2.pk)],
            archive_task.si.call_args_list)
        self.assertEqual(
            [mock.call(item4.pk, item3.pk), mock.call(item2.pk, item1.pk)],
            link_task.si.call_args_list)


class LinkArtifactInArchiveTaskTest(LocalArchiveTestBase):

    def test_link_artifact_in_archive(self):
        """
        The link_artifact_in_archive task should use the transport to link the
        specified artifacts.
        """
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        build = BuildFactory.create(job=dependency.job, phase=Build.FINALIZED)
        artifact = ArtifactFactory.create(
            build=build, filename="testing/testing.txt")

        # We need to ensure that the artifacts are all connected up.
        process_build_dependencies(build.pk)

        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir, default=True)
        [item1, item2] = archive.add_build(artifact.build)[artifact]
        item1.archived_size = 1000
        item1.save()

        transport = mock.Mock(spec=LocalTransport)
        with mock.patch.object(
                Archive, "get_transport", return_value=transport):
            link_artifact_in_archive(item1.pk, item2.pk)

        transport.link_filename_to_filename.assert_called_once_with(
            item1.archived_path, item2.archived_path)
        transport.link_to_current.assert_called_once_with(item2.archived_path)
        item1 = ArchiveArtifact.objects.get(pk=item1.pk)
        self.assertEqual(1000, item1.archived_size)

    def test_archive_artifact_from_non_finalized_projectbuild(self):
        """
        If the build is complete, and the item being archived is in a FINALIZED
        ProjectBuild, it should use the transport to set the current directory
        correctly.
        """
        project = ProjectFactory.create()
        dependency1 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency1)

        dependency2 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency2)

        projectbuild = build_project(project, queue_build=False)
        BuildFactory.create(
            job=dependency1.job, build_id=projectbuild.build_key,
            phase=Build.STARTED)
        build2 = BuildFactory.create(
            job=dependency2.job, build_id=projectbuild.build_key,
            phase=Build.FINALIZED)

        artifact = ArtifactFactory.create(
            build=build2, filename="testing/testing.txt")

        # We need to ensure that the artifacts are all connected up.
        process_build_dependencies(build2.pk)

        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir, default=True)
        [item1, item2] = archive.add_build(artifact.build)[artifact]

        transport = LoggingTransport(archive)
        with mock.patch.object(
                Archive, "get_transport", return_value=transport):
            link_artifact_in_archive(item1.pk, item2.pk)

        # As this projectbuild is only partially built, we shouldn't make this
        # the current build.
        self.assertEqual(
            ["START",
             "Link %s to %s" % (item1.archived_path, item2.archived_path),
             "END"],
            transport.log)

    def test_archive_artifact_from_finalized_projectbuild(self):
        """
        If the build is complete, and the item being archived is in a FINALIZED
        ProjectBuild, it should use the transport to set the current directory
        correctly.
        """
        project = ProjectFactory.create()
        dependency1 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency1)

        dependency2 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency2)

        projectbuild = build_project(project, queue_build=False)
        build1 = BuildFactory.create(
            job=dependency1.job, build_id=projectbuild.build_key,
            phase=Build.FINALIZED)
        build2 = BuildFactory.create(
            job=dependency2.job, build_id=projectbuild.build_key,
            phase=Build.FINALIZED)

        artifact = ArtifactFactory.create(
            build=build2, filename="testing/testing.txt")

        # We need to ensure that the artifacts are all connected up.
        process_build_dependencies(build1.pk)
        process_build_dependencies(build2.pk)

        archive = ArchiveFactory.create(
            transport="local", basedir=self.basedir, default=True)
        [item1, item2] = archive.add_build(artifact.build)[artifact]

        transport = LoggingTransport(archive)
        with mock.patch.object(
                Archive, "get_transport", return_value=transport):
            link_artifact_in_archive(item1.pk, item2.pk)

        # Both builds are complete, we expect this to be made the current
        # build.
        self.assertEqual(
            ["START",
             "Link %s to %s" % (item1.archived_path, item2.archived_path),
             "Make %s current" % item2.archived_path,
             "END"],
            transport.log)
