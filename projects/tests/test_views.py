from django.core.urlresolvers import reverse
from django.contrib.auth.models import User

from django_webtest import WebTest
import mock

from jenkins.models import Job, Build
from jenkins.tasks import delete_job_from_jenkins
from jenkins.tests.factories import (
    BuildFactory, JobFactory, JobTypeFactory, JenkinsServerFactory,
    job_with_parameters, ArtifactFactory)
from projects.models import (
    ProjectDependency, Project, Dependency, ProjectBuildDependency)
from projects.helpers import build_project
from projects.tasks import process_build_dependencies

from .factories import (
    ProjectFactory, DependencyFactory, ProjectBuildFactory)
from archives.tests.factories import ArchiveFactory


# TODO Introduce subclass of WebTest that allows easy assertions that a page
# requires various permissions...
# Possibly, through looking to see if Views are mixed in with the various
# Django-Braces mixins.
from projects.views import DependencyDetailView, ProjectDetailView


class ProjectDetailTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_project_detail(self):
        """
        The detail view should render the project.
        """
        project = ProjectFactory.create()
        # TODO: Work out how to configure DjangoFactory to setup m2m through
        dependency = ProjectDependency.objects.create(
            project=project, dependency=DependencyFactory.create())
        # TODO: It'd be nice if this was driven by ProjectBuildFactory.
        projectbuilds = [
            build_project(project, queue_build=False) for x in range(6)]

        project_url = reverse("project_detail", kwargs={"pk": project.pk})
        response = self.app.get(project_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(project, response.context["project"])
        self.assertEqual([dependency], list(response.context["dependencies"]))

        self.assertEqual(
            sorted(projectbuilds[1:], key=lambda x: x.build_id, reverse=True),
            list(response.context["projectbuilds"]))

    def test_project_detail_artifacts(self):
        """
        The project detail should return artifacts with the URL from Jenkins or
        from the archive (for archived artifacts).
        """
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(project=project, dependency=dependency)

        projectbuild = build_project(project, queue_build=False)
        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key,
            phase=Build.FINALIZED)

        artifact = ArtifactFactory.create(build=build, filename="file1.gz")
        process_build_dependencies(build.pk)

        # The project detail should link to the artifact from Jenkins
        project_url = reverse("project_detail", kwargs={"pk": project.pk})
        response = self.app.get(project_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertIsNotNone(
            response.context["project"].get_current_projectbuild())
        self.assertEqual(
            [ProjectDetailView.item_from_artifact(artifact)],
            response.context["current_artifacts"])

        # Archive the artifact and the view should display the archived item
        archive = ArchiveFactory.create(policy="cdimage", default=True)
        items = []
        for x in archive.add_build(build)[artifact]:
            if x.projectbuild_dependency:
                items.append(ProjectDetailView.item_from_archived_artifact(x))

        project_url = reverse("project_detail", kwargs={"pk": project.pk})
        response = self.app.get(project_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(items, response.context["current_artifacts"])

    def test_item_from_artifact_and_archived_artifact(self):
        """
        Return an artifact or archived artifact in a standard format for
        display.
        """
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(project=project, dependency=dependency)

        projectbuild = build_project(project, queue_build=False)
        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key,
            phase=Build.FINALIZED)

        # Create the artifact and check the display format
        artifact = ArtifactFactory.create(build=build, filename="file1.gz")
        artifact_item = ProjectDetailView.item_from_artifact(artifact)
        self.assertIsNotNone(artifact_item)
        self.assertTrue(isinstance(artifact_item, dict))
        self.assertTrue("build_name" in artifact_item)
        self.assertTrue("filename" in artifact_item)
        self.assertTrue("url" in artifact_item)
        self.assertTrue("archived" in artifact_item)

        # Archive the artifact and check the display format
        process_build_dependencies(build.pk)
        archive = ArchiveFactory.create(policy="cdimage", default=True)
        items = []
        for x in archive.add_build(build)[artifact]:
            if x.projectbuild_dependency:
                items.append(x)
        self.assertEquals(len(items), 1)
        archived_item = ProjectDetailView.item_from_archived_artifact(items[0])
        self.assertIsNotNone(archived_item)
        self.assertTrue(isinstance(archived_item, dict))
        self.assertTrue("build_name" in archived_item)
        self.assertTrue("filename" in archived_item)
        self.assertTrue("url" in archived_item)
        self.assertTrue("archived" in archived_item)


class ProjectCreateTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_superuser(
            "testing", "testing@example.com", "password")
        self.dependency1 = DependencyFactory.create()
        self.dependency2 = DependencyFactory.create()

    def test_page_requires_permission(self):
        """
        """
        # TODO: We should assert that requests without the
        # "projects.add_project" get redirected to login.

    def test_create_project_with_dependencies(self):
        """
        We can create projects with a set of dependencies.
        """
        project_url = reverse("project_create")
        response = self.app.get(project_url, user="testing")
        form = response.forms["project"]
        form["dependencies"].select_multiple(
            [self.dependency1.pk, self.dependency2.pk])
        form["name"].value = "My Project"

        response = form.submit()

        project = Project.objects.get(name="My Project")
        dependencies = ProjectDependency.objects.filter(project=project)

        self.assertEqual(
            [False, False],
            list(dependencies.values_list("auto_track", flat=True)))
        self.assertEqual(
            set([self.dependency1.name, self.dependency2.name]),
            set(dependencies.values_list("dependency__name", flat=True)))

    def test_create_project_with_auto_track(self):
        """
        We can set the auto_track on dependencies of the project.
        """
        project_url = reverse("project_create")
        response = self.app.get(project_url, user="testing")
        form = response.forms["project"]
        form["dependencies"].select_multiple(
            [self.dependency1.pk, self.dependency2.pk])
        form["name"].value = "My Project"
        form["auto_track"].value = True

        response = form.submit()

        project = Project.objects.get(name="My Project")
        dependencies = ProjectDependency.objects.filter(project=project)

        self.assertEqual(
            [True, True],
            list(dependencies.values_list("auto_track", flat=True)))

    def test_create_project_non_unique_name(self):
        """
        The project name should be unique.
        """
        ProjectFactory.create(name="My Project")

        project_url = reverse("project_create")
        response = self.app.get(project_url, user="testing")
        form = response.forms["project"]
        form["dependencies"].select_multiple(
            [self.dependency1.pk])
        form["name"].value = "My Project"

        response = form.submit()
        self.assertContains(response, "Project with this Name already exists.")


class ProjectBuildListTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_projectbuild_list_view(self):
        """
        The list view should provide a list of projects.
        """
        job = JobFactory.create()
        BuildFactory.create_batch(5, job=job)

        project = ProjectFactory.create()

        ProjectDependency.objects.create(
            project=project, dependency=DependencyFactory.create(job=job))
        projectbuild = ProjectBuildFactory.create(project=project)
        BuildFactory.create(job=job, build_id=projectbuild.build_id)

        url = reverse("project_projectbuild_list", kwargs={"pk": project.pk})
        response = self.app.get(url, user="testing")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            set([projectbuild]), set(response.context["projectbuilds"]))
        self.assertEqual(project, response.context["project"])


class ProjectBuildDetailTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")
        self.project = ProjectFactory.create()

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_project_build_detail_view(self):
        """
        Project build detail should show the build.
        """
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency)

        projectbuild = build_project(self.project, queue_build=False)
        BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key)

        url = reverse(
            "project_projectbuild_detail",
            kwargs={"project_pk": self.project.pk,
                    "build_pk": projectbuild.pk})
        response = self.app.get(url, user="testing")

        dependencies = ProjectBuildDependency.objects.filter(
            projectbuild=projectbuild)

        self.assertEqual(projectbuild, response.context["projectbuild"])
        self.assertEqual(
            list(dependencies), list(response.context["dependencies"]))
        self.assertTrue(
            "archived_items" not in response.context,
            "Project Build has archive items.")

    def test_project_build_detail_view_with_archived_artifacts(self):
        """
        If we have archived artifacts for this build, we should provide the list
        of archived items in the response context.
        """
        dependency = DependencyFactory.create()
        ProjectDependency.objects.create(
            project=self.project, dependency=dependency)

        projectbuild = build_project(self.project, queue_build=False)
        build = BuildFactory.create(
            job=dependency.job, build_id=projectbuild.build_key)
        artifact = ArtifactFactory.create(build=build, filename="file1.gz")

        process_build_dependencies(build.pk)
        archive = ArchiveFactory.create(policy="cdimage", default=True)
        items = [x for x in archive.add_build(build)[artifact] if x.projectbuild_dependency]

        url = reverse(
            "project_projectbuild_detail",
            kwargs={"project_pk": self.project.pk,
                    "build_pk": projectbuild.pk})
        response = self.app.get(url, user="testing")

        self.assertEqual(items, list(response.context["archived_items"]))


class DependencyListTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_dependency_list_view(self):
        """
        The Dependency List should render a list of dependencies with links to
        their type detail views.
        """
        dependencies = DependencyFactory.create_batch(5)
        url = reverse("dependency_list")
        response = self.app.get(url, user="testing")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            set(dependencies), set(response.context["dependencies"]))

        response = response.click(dependencies[0].job.jobtype.name)
        self.assertEqual(
            dependencies[0].job.jobtype.name, response.html.title.text)


class DependencyCreateTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_superuser(
            "testing", "testing@example.com", "password")
        self.jobtype = JobTypeFactory.create(
            config_xml="this is the job xml")
        self.server = JenkinsServerFactory.create()

    def test_page_requires_permission(self):
        """
        """
        # TODO: We should assert that requests without the
        # "projects.add_dependency" get redirected to login.

    def test_create_dependency(self):
        """
        We can create dependencies with jobs in servers.
        """
        project_url = reverse("dependency_create")
        response = self.app.get(project_url, user="testing")

        form = response.forms["dependency"]
        form["jobtype"].select(self.jobtype.pk)
        form["server"].select(self.server.pk)
        form["name"].value = "My Dependency"
        form["parameters"].value = "MYVALUE=this is a test\nNEWVALUE=testing"

        with mock.patch("projects.forms.push_job_to_jenkins") as job_mock:
            response = form.submit().follow()

        new_dependency = Dependency.objects.get(name="My Dependency")
        job = Job.objects.get(jobtype=self.jobtype, server=self.server)
        job_mock.delay.assert_called_once_with(job.pk)
        self.assertEqual(new_dependency.job, job)
        self.assertEqual(
            "MYVALUE=this is a test\nNEWVALUE=testing",
            new_dependency.parameters)

    def test_create_dependency_with_invalid_parameters(self):
        """
        If we attempt to create a dependency with invalid parameters, we should
        get an appropriate message.
        """
        project_url = reverse("dependency_create")
        response = self.app.get(project_url, user="testing")

        form = response.forms["dependency"]
        form["jobtype"].select(self.jobtype.pk)
        form["server"].select(self.server.pk)
        form["name"].value = "My Dependency"
        form["parameters"].value = "MYVALUE=this is a test NEWVALUE=testing"

        response = form.submit()
        self.assertContains(
            response,
            "Invalid parameters entered.  Must be separated by newline.")


class DependencyDetailTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_superuser(
            "testing", "testing@example.com", "password")

    def test_dependency_detail(self):
        """
        The dependency detail page should show recent builds, and associated
        projects.
        """
        dependency = DependencyFactory.create()
        project = ProjectFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        response = self.app.get(url, user="testing")

        self.assertEqual(dependency, response.context["dependency"])
        self.assertEqual([project], list(response.context["projects"]))
        self.assertNotContains(response, "Dependency currently building")

    def test_dependency_detail_with_currently_building(self):
        """
        If the Dependency is currently building, we should get an info message
        with this in the page.
        """
        dependency = DependencyFactory.create()
        BuildFactory.create(job=dependency.job, status="STARTED")
        url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        response = self.app.get(url, user="testing")

        self.assertContains(response, "Dependency currently building")

    def test_dependency_build(self):
        """
        It's possible to request a build of a dependency from the dependency
        detail page.
        """
        dependency = DependencyFactory.create()
        project = ProjectFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        response = self.app.get(url, user="testing")

        with mock.patch("projects.helpers.build_job") as build_job_mock:
            response = response.forms["build-dependency"].submit().follow()

        self.assertEqual(dependency, response.context["dependency"])
        self.assertEqual([project], list(response.context["projects"]))
        self.assertContains(
            response, "Build for '%s' queued." % dependency.name)
        build_job_mock.delay.assert_called_once_with(
            dependency.job.pk, user=self.user.username)

    def test_dependency_build_with_parameters(self):
        """
        If the dependency we're building has parameters, these should be passed
        with the job queue.
        """
        dependency = DependencyFactory.create(parameters="TESTPARAMETER=500")
        project = ProjectFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        response = self.app.get(url, user="testing")

        with mock.patch("projects.helpers.build_job") as build_job_mock:
            response = response.forms["build-dependency"].submit().follow()

        self.assertEqual(dependency, response.context["dependency"])
        self.assertEqual([project], list(response.context["projects"]))
        self.assertContains(
            response, "Build for '%s' queued." % dependency.name)
        build_job_mock.delay.assert_called_once_with(
            dependency.job.pk, params={"TESTPARAMETER": "500"},
            user=self.user.username)

    def test_dependency_build_pagination(self):
        """
        The dependency build list should return maximum number records as
        defined in PAGINATE_BUILDS. The previous page link should be
        disabled and the next page link should be available.
        """
        dependency = DependencyFactory.create()
        BuildFactory.create_batch(
            DependencyDetailView.PAGINATE_BUILDS + 1, job=dependency.job)

        depend_url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        response = self.app.get(depend_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(response.context["builds"]),
                         DependencyDetailView.PAGINATE_BUILDS)
        self.assertEqual(response.context["builds"].number, 1)

        # Check that the 'Newer' link is disabled
        self.assertRaises(IndexError, response.click, "Newer")

        # Check that the 'Older' link takes us to page two
        older = response.click("Older")
        self.assertEqual(200, older.status_code)
        self.assertNotEquals(older, response)
        self.assertEqual(older.context["builds"].number, 2)

    def test_dependency_build_pagination_page_two(self):
        """
        The dependency build list should return 1 record when retrieving the
        second page.
        """
        dependency = DependencyFactory.create()
        BuildFactory.create_batch(
            DependencyDetailView.PAGINATE_BUILDS + 1, job=dependency.job)

        depend_url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        depend_url += "?page=2"
        response = self.app.get(depend_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(response.context["builds"]), 1)
        self.assertEqual(response.context["builds"].number, 2)

        # Check that the 'Older' link is disabled
        self.assertRaises(IndexError, response.click, "Older")

        # Check that the 'newer' link takes us to page one
        newer = response.click("Newer")
        self.assertEqual(200, newer.status_code)
        self.assertNotEquals(newer, response)
        self.assertEqual(newer.context["builds"].number, 1)

    def test_dependency_build_pagination_page_non_numeric(self):
        """
        The dependency build list should return page 1 when a non-numeric
        page is supplied.
        """
        dependency = DependencyFactory.create()
        BuildFactory.create_batch(
            DependencyDetailView.PAGINATE_BUILDS + 1, job=dependency.job)

        depend_url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        depend_url += "?page=abc"
        response = self.app.get(depend_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(response.context["builds"]),
                         DependencyDetailView.PAGINATE_BUILDS)
        self.assertEqual(response.context["builds"].number, 1)

    def test_dependency_build_pagination_page_invalid(self):
        """
        The dependency build list should return the last page when an out-of-
        range number is supplied.
        """
        dependency = DependencyFactory.create()
        BuildFactory.create_batch(
            DependencyDetailView.PAGINATE_BUILDS + 1, job=dependency.job)

        depend_url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        depend_url += "?page=999"
        response = self.app.get(depend_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(response.context["builds"]), 1)
        self.assertEqual(response.context["builds"].number, 2)


class DependencyUpdateTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_superuser(
            "testing", "testing@example.com", "password")

    def test_dependency_update(self):
        """
        We can go from the DependencyDetail view to the DependencyUpdateView
        and modify the parameters for a Job.
        """
        dependency = DependencyFactory.create()
        project = ProjectFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        response = self.app.get(url, user="testing")

        response = response.click("Edit dependency")

        form = response.forms["dependency"]
        form["parameters"] = "TESTING=2\n"
        form["name"] = "My New Dependency"
        form["description"] = "New Description"

        self.assertNotIn("job", form.fields)
        response = form.submit()

        dependency = Dependency.objects.get(pk=dependency.pk)
        self.assertEqual("My New Dependency", dependency.name)
        self.assertEqual("New Description", dependency.description)
        self.assertEqual("TESTING=2\n", dependency.parameters)

    def test_dependency_update_with_bad_parameters(self):
        """
        When updating a dependency, we shouldn't allow badly formed
        parameters.
        """
        dependency = DependencyFactory.create()
        project = ProjectFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        response = self.app.get(url, user="testing")

        response = response.click("Edit dependency")

        form = response.forms["dependency"]
        form["parameters"] = "TESTING=2 TESTING=3\n"

        response = form.submit()
        self.assertContains(
            response,
            "Invalid parameters entered.  Must be separated by newline.")

    def test_dependency_update_context_has_parameters(self):
        """
        The dependency update view should include the list of parameters in the
        jobtype, excluding the BUILD_ID.
        """
        dependency = DependencyFactory.create()
        dependency.job.jobtype.config_xml = job_with_parameters
        dependency.job.jobtype.save()
        project = ProjectFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        url = reverse("dependency_update", kwargs={"pk": dependency.pk})
        response = self.app.get(url, user="testing")

        self.assertEqual([
              {"name": "BRANCH_TO_CHECKOUT",
               "description": "Branch to checkout and build.",
               "defaultValue": "http:///launchpad.net/mybranch"}],
            response.context["parameters"])


class InitiateProjectBuildTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_superuser(
            "testing", "testing@example.com", "password")

    def test_page_requires_permission(self):
        """
        """
        # TODO: We should assert that requests without the
        # "projects.add_projectbuild" get redirected to login.

    def test_project_build_form_selected_dependencies(self):
        """
        We expect all dependencies to be selected by default.
        """
        [dep1, dep2, dep3] = DependencyFactory.create_batch(3)
        project = ProjectFactory.create()
        for dep in [dep1, dep2, dep3]:
            ProjectDependency.objects.create(
                project=project, dependency=dep)
        url = reverse(
            "project_initiate_projectbuild", kwargs={"pk": project.pk})
        response = self.app.get(url, user="testing")
        form = response.forms["buildproject-form"]
        # We expect all dependencies to be selected by default
        self.assertEqual(
            [str(x.pk) for x in [dep1, dep2, dep3]],
            [x.value for x in form.fields["dependencies"]])

        with mock.patch("projects.helpers.build_job") as build_job_mock:
            response = form.submit().follow()

        projectbuild = response.context["projectbuild"]

        build_job_mock.delay.assert_has_calls([
            mock.call(dep1.job.pk, build_id=projectbuild.build_key,
                      user='testing'),
            mock.call(dep2.job.pk, build_id=projectbuild.build_key,
                      user='testing'),
            mock.call(dep3.job.pk, build_id=projectbuild.build_key,
                      user='testing')])
        self.assertContains(
            response, "Build '%s' queued." % projectbuild.build_id)

    def test_project_build_form_builds_only_selected(self):
        """
        We expect all dependencies to be selected by default.
        """
        [dep1, dep2, dep3] = DependencyFactory.create_batch(3)
        project = ProjectFactory.create()
        for dep in [dep1, dep2, dep3]:
            ProjectDependency.objects.create(
                project=project, dependency=dep)
        url = reverse(
            "project_initiate_projectbuild", kwargs={"pk": project.pk})
        response = self.app.get(url, user="testing")
        form = response.forms["buildproject-form"]

        form["dependencies"] = [str(dep1.pk), str(dep3.pk)]

        with mock.patch("projects.helpers.build_job") as build_job_mock:
            response = form.submit().follow()

        projectbuild = response.context["projectbuild"]

        build_job_mock.delay.assert_has_calls([
            mock.call(dep1.job.pk, build_id=projectbuild.build_key,
                      user='testing'),
            mock.call(dep3.job.pk, build_id=projectbuild.build_key,
                      user='testing')])

    def test_project_build_form_requires_selection(self):
        """
        If no dependencies are selected, then we should get an appropriate
        error.
        """
        [dep1, dep2, dep3] = DependencyFactory.create_batch(3)
        project = ProjectFactory.create()
        for dep in [dep1, dep2, dep3]:
            ProjectDependency.objects.create(
                project=project, dependency=dep)
        url = reverse(
            "project_initiate_projectbuild", kwargs={"pk": project.pk})
        response = self.app.get(url, user="testing")
        form = response.forms["buildproject-form"]

        form["dependencies"] = []

        with mock.patch("projects.helpers.build_job") as build_job_mock:
            response = form.submit()

        self.assertContains(response, "Must select at least one dependency.")
        self.assertEqual([], build_job_mock.delay.mock_calls)


class ProjectUpdateTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_superuser(
            "testing", "testing@example.com", "password")

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_project_update(self):
        """
        The update view should allow us to change the auto track status of the
        dependencies and add additional dependencies.
        """
        project = ProjectFactory.create()
        # TODO: Work out how to configure DjangoFactory to setup m2m through
        projectdependency1 = ProjectDependency.objects.create(
            project=project, dependency=DependencyFactory.create())

        projectdependency2 = ProjectDependency.objects.create(
            project=project, dependency=DependencyFactory.create())

        project_url = reverse("project_update", kwargs={"pk": project.pk})
        response = self.app.get(project_url, user="testing")
        self.assertEqual(200, response.status_code)

        form = response.forms["project"]
        self.assertEqual(
            [str(projectdependency1.dependency.pk),
             str(projectdependency2.dependency.pk)],
            sorted(form["dependencies"].value))
        self.assertEqual(project.name, form["name"].value)

        form["dependencies"].select_multiple(
            [projectdependency2.dependency.pk])
        form.submit().follow()

        self.assertEqual(1, len(project.dependencies.all()))


class ProjectDependenciesTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_project_dependencies(self):
        """
        Project Dependencies view should show all dependencies and the status
        of their build.
        """
        project = ProjectFactory.create()
        dependency = DependencyFactory.create()
        builds = BuildFactory.create_batch(5, job=dependency.job)
        ProjectDependency.objects.create(
            project=project, dependency=dependency, auto_track=False,
            current_build=builds[-1])

        project_url = reverse(
            "project_dependencies", kwargs={"pk": project.pk})
        response = self.app.get(project_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(project, response.context["project"])

        self.assertEqual(
            [dependency],
            list(response.context["builds_header"]))


class DependencyDeleteTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_superuser(
            "testing", "testing@example.com", "password")

    def test_dependency_delete(self):
        """
        We can delete Dependencies that are not associated with any Projects.
        """
        dependency = DependencyFactory.create()
        url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        response = self.app.get(url, user="testing")

        response = response.click("Delete dependency")
        self.assertNotContains(
            response,
            "This dependency cannot be deleted because it has associated "
            "projects.")
        self.assertContains(
            response,
            "This will delete this dependency and the Jenkins job that it "
            "relies on.")

        with mock.patch("projects.views.delete_job_from_jenkins") as task_mock:
            response = response.form.submit().follow()

        task_mock.delay.assert_called_once_with(dependency.job.pk)
        self.assertContains(
            response, "Dependency '%s' deleted." % dependency.name)
        self.assertIsNone(Dependency.objects.filter(pk=dependency.pk).first())

    def test_dependency_delete_associated_with_a_project(self):
        """
        If a Dependency is associated with a Project, we get an appropriate
        error message.
        """
        dependency = DependencyFactory.create()
        project = ProjectFactory.create()
        ProjectDependency.objects.create(
            project=project, dependency=dependency)
        url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        response = self.app.get(url, user="testing")

        response = response.click("Delete dependency")

        self.assertContains(
            response,
            "This dependency cannot be deleted because it has associated "
            "projects.")
        self.assertNotContains(
            response,
            "This will delete this dependency and the Jenkins job that it "
            "relies on.")
