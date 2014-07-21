from __future__ import unicode_literals

from django.test import TestCase

from archives.models import Archive, ArchiveArtifact
from archives.policies import DefaultPolicy, CdimageArchivePolicy
from archives.transports import SshTransport, LocalTransport

from jenkins.tests.factories import BuildFactory, ArtifactFactory
from projects.tasks import (
    update_projectbuilds, create_projectbuilds_for_autotracking)
from projects.tests.factories import DependencyFactory, ProjectFactory
from projects.models import ProjectDependency
from credentials.tests.factories import SshKeyPairFactory
from .factories import ArchiveFactory
from projects.helpers import build_project


class ArchiveTest(TestCase):
    def setUp(self):
        self.credentials = SshKeyPairFactory.create()

    def test_instantiation(self):
        """We can instantiate an Archive."""
        Archive.objects.create(
            name="My Test Archive",
            host="archive.example.com",
            policy="cdimage",
            transport="ssh",
            basedir="/var/tmp",
            username="testing",
            ssh_credentials=self.credentials)

    def create_dependencies(self, count=1, name="Project 1"):
        """
        Utility function to create projects and dependencies.
        """
        project = ProjectFactory.create(name=name)
        dependencies = [project]
        for x in range(count):
            dependency = DependencyFactory.create()
            ProjectDependency.objects.create(
                project=project, dependency=dependency)
            dependencies.append(dependency)
        return dependencies

    def test_get_transport(self):
        """
        Archive.get_transport should return the class to be used when moving
        files to an archive store.
        """
        archive = ArchiveFactory.create(transport="ssh")
        self.assertIsInstance(archive.get_transport(), SshTransport)

        archive.transport = "local"
        self.assertIsInstance(archive.get_transport(), LocalTransport)

    def test_get_policy(self):
        """
        Archive.get_policy should return the class to be used when deciding the
        names for files in the archive store.
        """
        archive = ArchiveFactory.create(policy="default")
        self.assertIsInstance(archive.get_policy(), DefaultPolicy)

    def test_add_build_from_dependency(self):
        """
        Adding a dependency build (i.e. not a ProjectBuild) should result in a
        single item in the archive.
        """
        project, dependency = self.create_dependencies()

        build = BuildFactory.create(job=dependency.job)
        artifact = ArtifactFactory.create(build=build, filename="testing.gz")
        archive = ArchiveFactory.create()

        items = archive.add_build(build)
        self.assertEqual(1, archive.items.count())
        self.assertEqual([artifact], [x.artifact for x in items[artifact]])

        policy_path = archive.get_policy().get_path_for_artifact(
            artifact, build=build, dependency=dependency)
        self.assertEqual(
            policy_path,
            archive.items.first().archived_path)

    def test_artifact_get_url(self):
        """
        ArchiveArtifact.get_url should return a valid URL for an artifact within
        the archive.
        """
        project, dependency = self.create_dependencies()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)

        projectbuild = build_project(project, queue_build=False)

        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key)

        artifact = ArtifactFactory.create(build=build, filename="file1.gz")
        archive = ArchiveFactory.create(policy="cdimage")
        update_projectbuilds(build)
        create_projectbuilds_for_autotracking(build)
        archive.add_build(build)

        [item1, item2] = list(archive.get_archived_artifacts_for_build(build))

        self.assertEqual(
            "http://example.com/projects/%s" % item1.archived_path,
            item1.get_url())
        self.assertEqual(
            "http://example.com/projects/%s" % item2.archived_path,
            item2.get_url())

    def test_get_archived_artifacts_for_build(self):
        """
        We can fetch the artifacts that get added from a build.
        """
        dependency = DependencyFactory.create()

        build = BuildFactory.create(job=dependency.job)
        artifact = ArtifactFactory.create(build=build, filename="testing.gz")
        archive = ArchiveFactory.create()

        archive.add_build(build)

        archived = list(archive.get_archived_artifacts_for_build(build))
        self.assertEqual(
            [(artifact, build)],
            [(x.artifact, x.build) for x in archived])

    def test_get_archived_artifact_artifact_not_in_archive(self):
        """
        If the specified build is not recorded in the archive then we should
        get an empty set back.
        """
        dependency = DependencyFactory.create()
        build = BuildFactory.create(job=dependency.job)
        ArtifactFactory.create(build=build)
        archive = ArchiveFactory.create()

        self.assertEqual(
            0,
            archive.get_archived_artifacts_for_build(build).count())

    def test_archive_build_projectbuild(self):
        """
        The archiver can handle archiving a build from a projectbuild.
        """
        project, dependency1, dependency2 = self.create_dependencies(2)

        ProjectDependency.objects.create(
            project=project, dependency=dependency2)
        projectbuild = build_project(project, queue_build=False)

        archive = ArchiveFactory.create(policy="cdimage")

        build1 = BuildFactory.create(
            job=dependency1.job, build_id=projectbuild.build_key)
        artifact1 = ArtifactFactory.create(
            build=build1, filename="artifact1.gz")

        update_projectbuilds(build1)
        build1_items = archive.add_build(build1)
        self.assertEqual(2, len(build1_items[artifact1]))

        build2 = BuildFactory.create(
            job=dependency2.job, build_id=projectbuild.build_key)
        artifact2 = ArtifactFactory.create(build=build2, filename="artifact2.gz")

        update_projectbuilds(build2)
        build2_items = archive.add_build(build2)
        self.assertEqual(2, len(build2_items[artifact2]))

        self.assertEqual(4, archive.items.count())

        self.assertEqual(
            2,
            ArchiveArtifact.objects.filter(
                projectbuild_dependency__projectbuild=projectbuild).count())

    def test_cdimage_archiver_policy_with_only_dependency_build(self):
        """
        If we only build a dependency with no project builds, then the cdimage
        archiver should delegate to the default policy for the name when
        generating the archive name for the dependency's artifacts.
        """
        dependency = DependencyFactory.create()
        build = BuildFactory.create(job=dependency.job)

        artifact = ArtifactFactory.create(build=build, filename="testing.gz")
        update_projectbuilds(build)

        archive = ArchiveFactory.create(policy="cdimage")
        archive.add_build(build)

        archived = archive.get_archived_artifacts_for_build(build).order_by(
            "archived_path")
        name = DefaultPolicy().get_path_for_artifact(
            artifact, build=build, dependency=dependency)
        self.assertEqual(
            name,
            "\n".join(archived.values_list("archived_path", flat=True)))
        self.assertEqual(
            [None], list(archived.values_list("archived_at", flat=True)))

    def test_cdimage_archiver_policy(self):
        """
        If we use the cdimage policy, then the file path but should delegate to
        the default policy for builds without a projectbuild.
        """
        project, dependency = self.create_dependencies()
        projectbuild = build_project(project, queue_build=False)

        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key)

        ArtifactFactory.create(build=build, filename="testing.gz")
        update_projectbuilds(build)

        archive = ArchiveFactory.create(policy="cdimage")
        archive.add_build(build)

        archived = archive.get_archived_artifacts_for_build(build).order_by(
            "archived_path")
        policy = CdimageArchivePolicy()
        paths = []
        for item in archived:
            projectbuild = (item.projectbuild_dependency and
                            item.projectbuild_dependency.projectbuild or None)
            paths.append(policy.get_path_for_artifact(
                item.artifact, build=build, dependency=item.dependency,
                projectbuild=projectbuild))
        self.assertEqual(
            "\n".join(paths),
            "\n".join(archived.values_list("archived_path", flat=True)))

    def test_archive_build_several_projectbuild_dependencies(self):
        """
        If we archive a build that is used in several projectbuilds, then we
        should get multiple copies of the artifact.
        """
        project1, dependency1, dependency2 = self.create_dependencies(
            2)
        project2 = ProjectFactory.create(name="Project 2")
        ProjectDependency.objects.create(
            project=project2, dependency=dependency1)

        projectbuild = build_project(project1, queue_build=False)

        build1 = BuildFactory.create(
            job=dependency1.job, build_id=projectbuild.build_key)
        build2 = BuildFactory.create(
            job=dependency2.job, build_id=projectbuild.build_key)

        artifact1 = ArtifactFactory.create(build=build1, filename="file1.gz")
        artifact2 = ArtifactFactory.create(build=build2, filename="file2.gz")
        archive = ArchiveFactory.create(policy="cdimage")

        update_projectbuilds(build1)
        create_projectbuilds_for_autotracking(build1)
        archive.add_build(build1)
        self.assertEqual(3, archive.items.count())

        update_projectbuilds(build2)
        create_projectbuilds_for_autotracking(build2)
        archive.add_build(build2)
        self.assertEqual(5, archive.items.count())

        artifacts = ArchiveArtifact.objects.all().order_by("archived_path")
        policy = CdimageArchivePolicy()
        self.assertEqual(
            "{dependency1}\n{dependency2}\n"
            "project-1/{build}/file1.gz\nproject-1/{build}/file2.gz\n"
            "project-2/{build}/file1.gz".format(
                dependency1=policy.get_path_for_artifact(
                    artifact=artifact1, build=build1, dependency=dependency1),
                dependency2=policy.get_path_for_artifact(
                    artifact=artifact2, build=build2, dependency=dependency2),
                build=projectbuild.build_id),
            "\n".join(artifacts.values_list("archived_path", flat=True)))
