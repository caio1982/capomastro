from __future__ import unicode_literals
from datetime import timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from jenkins.models import Build

from projects.models import (
    Dependency, ProjectDependency, ProjectBuild, generate_projectbuild_id)
from projects.tasks import process_build_dependencies
from .factories import (
    ProjectFactory, DependencyFactory, ProjectBuildFactory)
from jenkins.tests.factories import JobFactory, BuildFactory, ArtifactFactory


class DependencyTest(TestCase):

    def test_instantiation(self):
        """We can create Dependencies."""
        job = JobFactory.create()
        Dependency.objects.create(
            name="My Dependency", job=job)

    def test_get_current_build(self):
        """
        Dependency.get_current_build should return the most recent build that
        has completed and was SUCCESSful.
        """
        build1 = BuildFactory.create()
        build2 = BuildFactory.create(
            phase=Build.FINALIZED, status="SUCCESS", job=build1.job)
        dependency = DependencyFactory.create(job=build1.job)
        self.assertEqual(build2, dependency.get_current_build())

    def test_get_current_build_with_no_builds(self):
        """
        If there are no current builds for a given dependency, then we should
        get None.
        """
        dependency = DependencyFactory.create()
        self.assertEqual(None, dependency.get_current_build())

    def test_get_parameters(self):
        """
        Dependency.get_build_parameters should return a dictionary parsed from
        the parameters property.
        """
        dependency = DependencyFactory.create(
            parameters="THISVALUE=testing\nTHATVALUE=55")
        self.assertEqual(
            {"THISVALUE": "testing", "THATVALUE": "55"},
            dependency.get_build_parameters())

    def test_get_parameters_with_no_parameters(self):
        """
        Dependency.get_build_parameters should None if there are no build
        parameters.
        """
        dependency = DependencyFactory.create(parameters=None)
        self.assertIsNone(dependency.get_build_parameters())

    def test_get_parameters_with_multiple_items_on_one_line(self):
        """
        If we have more than one parameter on one line, it's invalid, and so we
        should not get an error.
        """
        dependency = DependencyFactory.create(parameters='TESTING1="testing" TESTING2="testing"')
        self.assertIsNone(dependency.get_build_parameters())

    def test_is_dependency_building(self):
        """
        is_building should return True if we have an active build for
        this dependency in the works.
        """
        dependency = DependencyFactory.create()
        self.assertFalse(dependency.is_building)

        BuildFactory.create(job=dependency.job)
        self.assertTrue(dependency.is_building)


class ProjectDependencyTest(TestCase):

    def test_instantiation(self):
        """We can create ProjectDependency objects."""
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        self.assertEqual(
            set([dependency]), set(project.dependencies.all()))


class ProjectTest(TestCase):

    def test_get_current_artifacts(self):
        """
        Project.get_current_artifacts returns the current set of artifacts
        for this project.
        """
        project = ProjectFactory.create()
        job = JobFactory.create()
        dependency = DependencyFactory.create(job=job)
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        build1 = BuildFactory.create(job=job)
        build2 = BuildFactory.create(job=job)

        ArtifactFactory.create(build=build1)
        artifact2 = ArtifactFactory.create(build=build2)

        process_build_dependencies(build2.pk)

        self.assertEqual([artifact2], list(project.get_current_artifacts()))

    def test_get_current_projectbuild(self):
        """
        Project.get_current_projectbuild returns the most recent ProjectBuild
        for this project.
        """
        project = ProjectFactory.create()
        dependency1 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency1)

        dependency2 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency2)

        from projects.helpers import build_project
        build1 = build_project(project, queue_build=False)
        build2 = build_project(project, queue_build=False)

        now = timezone.now()
        test_data = [
            (Build.FINALIZED, Build.STARTED, now - timedelta(hours=1), None, build1),
            (Build.FINALIZED, Build.FINALIZED, now - timedelta(hours=1), now, build2)
        ]

        for case in test_data:
            (phase1, phase2, end1, end2, result) = case
            build1.phase = phase1
            build1.ended_at = end1
            build1.save()

            build2.phase = phase2
            build2.ended_at = end2
            build2.save()
            self.assertEqual(result, project.get_current_projectbuild())


class ProjectBuildTest(TestCase):

    def setUp(self):
        self.project = ProjectFactory.create()
        self.user = User.objects.create_user("testing")

    def test_generate_projectbuild_id(self):
        """
        generate_projectbuild_id should generate an id using the date and the
        sequence of builds on that date.

        e.g. 20140312.1 is the first build on the 12th March 2014
        """
        build1 = ProjectBuildFactory.create()
        expected_build_id = timezone.now().strftime("%Y%m%d.1")
        self.assertEqual(expected_build_id, generate_projectbuild_id(build1))
        build2 = ProjectBuildFactory.create(project=build1.project)
        expected_build_id = timezone.now().strftime("%Y%m%d.2")
        self.assertEqual(expected_build_id, generate_projectbuild_id(build2))

    def test_build_key(self):
        """
        The build_key is a UUID for this project build.
        """
        build1 = ProjectBuildFactory.create()
        build2 = ProjectBuildFactory.create(project=build1.project)
        self.assertNotEqual(build1.build_key, build2.build_key)

    def test_instantiation(self):
        """
        We can create ProjectBuilds.
        """
        projectbuild = ProjectBuild.objects.create(
            project=self.project, requested_by=self.user)
        self.assertEqual(self.user, projectbuild.requested_by)
        self.assertIsNotNone(projectbuild.requested_at)
        self.assertIsNone(projectbuild.ended_at)
        self.assertEqual("UNKNOWN", projectbuild.status)
        self.assertEqual("UNKNOWN", projectbuild.phase)
        self.assertTrue(projectbuild.build_key)

    def test_build_id(self):
        """
        When we create a project build, we should create a unique id for the
        build.
        """
        projectbuild = ProjectBuildFactory.create()
        expected_build_id = timezone.now().strftime("%Y%m%d.0")
        self.assertEqual(expected_build_id, projectbuild.build_id)

    def test_can_be_archived(self):
        """
        A ProjectBuild knows whether or not it's ready to be archived.
        """
        dependency1 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency1)

        dependency2 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency2)

        from projects.helpers import build_project
        projectbuild = build_project(self.project, queue_build=False)

        # Current status is STARTED so we can't archive this build.
        self.assertEqual("UNKNOWN", projectbuild.phase)
        self.assertFalse(projectbuild.can_be_archived)

        builds = []
        for job in [dependency1.job, dependency2.job]:
            build = BuildFactory.create(
                job=job, build_id=projectbuild.build_key,
                phase=Build.FINALIZED)
            builds.append(build)
            process_build_dependencies(build.pk)
        projectbuild = ProjectBuild.objects.get(pk=projectbuild.pk)
        self.assertEqual(Build.FINALIZED, projectbuild.phase)

        self.assertFalse(
            projectbuild.can_be_archived,
            "Build with no artifacts can be archived")
        for build in builds:
            ArtifactFactory.create(build=build)
        self.assertTrue(
            projectbuild.can_be_archived,
            "Build with artifacts can't be archived")

        projectbuild.archived = timezone.now()
        self.assertFalse(projectbuild.can_be_archived)

    def test_can_be_archived_with_no_artifacts(self):
        """
        A projectbuild with no artifacts can't be archived.
        """
        dependency1 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency1)

        dependency2 = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency2)

        from projects.helpers import build_project
        projectbuild = build_project(self.project, queue_build=False)

        for job in [dependency1.job, dependency2.job]:
            BuildFactory.create(
                job=job, build_id=projectbuild.build_id, phase=Build.FINALIZED)
        projectbuild = ProjectBuild.objects.get(pk=projectbuild.pk)
        self.assertFalse(projectbuild.can_be_archived)
