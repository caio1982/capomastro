import json

from django.test import TestCase
from django.test.client import RequestFactory
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User

from django_webtest import WebTest
import mock

from jenkins.views import NotificationHandlerView
from jenkins.models import Build
from .factories import (
    JobFactory, JenkinsServerFactory, BuildFactory, JobTypeFactory)


class NotificationHandlerTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.view = NotificationHandlerView.as_view()
        self.server = JenkinsServerFactory.create()
        self.job = JobFactory(server=self.server, name="mytestjob")

    def _get_response_with_data(self, data, server_pk=None):
        server_pk = server_pk or self.server.pk
        request = self.factory.post(
            "/jenkins/notifications?server=%d" % server_pk,
            content_type="application/json",
            data=json.dumps(data))
        return self.view(request)

    def test_handle_notification_with_unknown_server_pk(self):
        """
        If we can't find the JenkinsServer using the remote_addr supplied in
        the request we should get a 412 response and log this.
        """
        notification = {}
        with mock.patch("jenkins.views.logging") as mock_logging:
            response = self._get_response_with_data(
                notification, 5)
            self.assertEqual(412, response.status_code)
            mock_logging.warn.assert_called_once_with(
                "Could not find server with Pk: 5")

    def test_handle_notification_with_unknown_job(self):
        """
        If we can't find the job referred to in the notification, we should get
        a 404 response?

        NOTE: The Jenkins notification plugin doesn't seem to care what
        response we send back...
        """
        notification = {
            "name": "unknown job",
            "build": {"phase": Build.FINALIZED, "number": 10}
        }
        with mock.patch("jenkins.views.logging") as mock_logging:
            response = self._get_response_with_data(
                notification)
            self.assertEqual(412, response.status_code)
            mock_logging.warn.assert_called_once_with(
                "Notification for unknown job 'unknown job'")

    def test_handle_notification_with_unknown_job_finalized(self):
        """
        If we can't find the job referred to in the notification, we should get
        a 404 response?

        NOTE: The Jenkins notification plugin doesn't seem to care what
        response we send back...
        """
        notification = {
            "name": "unknown job",
            "build": {"phase": Build.FINALIZED, "number": 10}
        }
        with mock.patch("jenkins.views.logging") as mock_logging:
            response = self._get_response_with_data(
                notification)
            self.assertEqual(412, response.status_code)
            mock_logging.warn.assert_called_once_with(
                "Notification for unknown job 'unknown job'")

    def test_handle_started_notification(self):
        """
        When a build starts we get a STARTED notification.
        """
        started = {
            "build": {
                "number": 11,
                "phase": "STARTED",
                "url": "job/mytestjob/11/"},
            "name": "mytestjob",
            "url": "job/mytestjob/"}
        self._get_response_with_data(started)

        self.assertEqual(1, Build.objects.count())
        build = Build.objects.get(job=self.job, number=11)
        self.assertEqual("", build.status)
        self.assertEqual(Build.STARTED, build.phase)

    def test_handle_started_notification_with_build_id(self):
        """
        If we have parameters and a BUILD_ID in the parameters, then we should
        store the BUILD_ID in the build.
        """
        started = {
            "build": {
                "number": 11,
                "phase": "STARTED",
                "parameters": {"BUILD_ID": "20140312.2"},
                "url": "job/mytestjob/11/"},
            "name": "mytestjob",
            "url": "job/mytestjob/"}
        self._get_response_with_data(started)

        build = Build.objects.get(job=self.job, number=11)
        self.assertEqual("20140312.2", build.build_id)

    def test_handle_completed_notification(self):
        """
        When a build starts we get a COMPLETED notification, we don't do
        anything for this phase.
        """
        completed = {
            "build": {
                "number": 11,
                "phase": "COMPLETED",
                "status": "SUCCESS",
                "url": "job/mytestjob/11/"},
            "name": "mytestjob",
            "url": "job/mytestjob/"}
        self._get_response_with_data(completed)
        self.assertEqual(0, Build.objects.count())

    def test_handle_finished_notification(self):
        """
        When a build has completed all the post-build operations, we get a
        FINISHED notification, this should trigger creation of a Build
        representing the FINALIZED build. The phase name should be translated
        from FINISHED to FINALIZED in the process. The name change was
        introduced in version 1.6 of the Jenkins Notifications plugin.
        """
        self.job.build_set.create(
            number=11,
            phase="STARTED")
        finished = {
            "build": {
                "number": 11,
                "phase": "FINISHED",
                "status": "SUCCESS",
                "url": "job/mytestjob/11/"},
            "name": "mytestjob",
            "url": "job/mytestjob/"}

        with mock.patch("jenkins.views.postprocess_build") as mock_postprocess_build:
            self._get_response_with_data(finished)

        build = Build.objects.get(job=self.job, number=11)
        self.assertEqual("SUCCESS", build.status)
        # This gets properly populated by the task that runs.
        self.assertEqual("job/mytestjob/11/", build.url)
        self.assertEqual(Build.FINALIZED, build.phase)
        mock_postprocess_build.assert_called_once_with(build)

    def test_handle_finalized_notification(self):
        """
        When a build has completed all the post-build operations, we get a
        FINALIZED notification (in later versions of the plugin), this should
        trigger creation of a Build representing the FINALIZED build.
        """
        self.job.build_set.create(
            number=11,
            phase="STARTED")
        finished = {
            "build": {
                "number": 11,
                "phase": "FINALIZED",
                "status": "SUCCESS",
                "url": "job/mytestjob/11/"},
            "name": "mytestjob",
            "url": "job/mytestjob/"}

        with mock.patch("jenkins.views.postprocess_build") as mock_postprocess_build:
            self._get_response_with_data(finished)

        build = Build.objects.get(job=self.job, number=11)
        self.assertEqual("SUCCESS", build.status)
        # This gets properly populated by the task that runs.
        self.assertEqual("job/mytestjob/11/", build.url)
        self.assertEqual(Build.FINALIZED, build.phase)
        mock_postprocess_build.assert_called_once_with(build)

    def test_handle_finalized_notification_with_no_started_build(self):
        """
        If we get a finished notification for a build we don't have any
        previous record of, we should still store it.
        """
        finished = {
            "build": {
                "number": 20,
                "phase": Build.FINALIZED,
                "status": "SUCCESS",
                "url": "job/mytestjob/20/"},
            "name": "mytestjob",
            "url": "job/mytestjob/"}

        with mock.patch("jenkins.views.postprocess_build") as mock_postprocess_build:
            self._get_response_with_data(finished)

        build = Build.objects.get(job=self.job, number=20)
        self.assertEqual("SUCCESS", build.status)
        # This gets properly populated by the task that runs.
        self.assertEqual("job/mytestjob/20/", build.url)
        self.assertEqual(Build.FINALIZED, build.phase)
        mock_postprocess_build.assert_called_once_with(build)

    def test_handle_finished_notification_with_build_id(self):
        """
        If we get a finished notfication for a build_id we don't have any
        previous record of, we should still store it.
        """
        finished = {
            "build": {
                "number": 20,
                "phase": "FINISHED",
                "status": "SUCCESS",
                "parameters": {"BUILD_ID": "20140312.2"},
                "url": "job/mytestjob/20/"},
            "name": "mytestjob",
            "url": "job/mytestjob/"}

        with mock.patch("jenkins.views.postprocess_build") as mock_postprocess_build:
            self._get_response_with_data(finished)

        build = Build.objects.get(job=self.job, number=20)
        self.assertEqual("20140312.2", build.build_id)
        mock_postprocess_build.assert_called_once_with(build)


class JenkinsServerIndexTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_server_index(self):
        """
        The index view should list all servers.
        """
        servers = JenkinsServerFactory.create_batch(5)
        response = self.app.get(reverse("jenkinsserver_list"), user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(servers, list(response.context["object_list"]))


class JenkinsServerDetailTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_server_detail(self):
        """
        The detail view should render the server and jobs for the server.
        """
        server = JenkinsServerFactory.create()
        jobs = JobFactory.create_batch(5, server=server)
        server_url = reverse("jenkinsserver_detail", kwargs={"pk": server.pk})
        response = self.app.get(server_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(server, response.context["server"])
        self.assertEqual(set(jobs), set(response.context["jobs"]))


class ServerJobBuildIndexTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_server_job_build_index(self):
        """
        The detail view should render the server, job and builds.
        """
        server = JenkinsServerFactory.create()
        job = JobFactory.create(server=server)
        builds = BuildFactory.create_batch(5, job=job)
        server_url = reverse(
            "jenkinsserver_job_builds_index",
            kwargs={"server_pk": server.pk, "job_pk": job.pk})
        response = self.app.get(server_url, user="testing")
        self.assertEqual(200, response.status_code)
        self.assertEqual(server, response.context["server"])
        self.assertEqual(job, response.context["job"])
        self.assertEqual(set(builds), set(response.context["builds"]))


class JobTypeDetailTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")

    def test_page_requires_authenticated_user(self):
        """
        """
        # TODO: We should assert that requests without a logged in user
        # get redirected to login.

    def test_jobtype_detail(self):
        """
        The detail view should render the job type name, description and
        the job xml.
        """
        jobtype = JobTypeFactory.create(
            config_xml="this is the job xml")
        jobtype_url = reverse(
            "jobtype_detail", kwargs={"pk": jobtype.pk})
        response = self.app.get(jobtype_url, user="testing")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            jobtype, response.context["jobtype"])

        self.assertContains(
            response, "<code>this is the job xml</code>", html=True)
        self.assertContains(response, jobtype.name)
        self.assertContains(response, jobtype.description)


class BuildDetailTest(WebTest):

    def setUp(self):
        self.user = User.objects.create_user("testing")

    def test_build_detail(self):
        """
        The build view should render the details for the build.
        """
        build = BuildFactory.create()
        build_url = reverse(
            "build_detail", kwargs={"pk": build.pk})
        response = self.app.get(build_url, user="testing")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            build, response.context["build"])

    def test_build_detail_console(self):
        """
        The build console view should render the console log for the build.
        """
        build = BuildFactory.create()
        build_url = reverse(
            "build_detail_console", kwargs={"pk": build.pk})
        response = self.app.get(build_url, user="testing")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            build, response.context["build"])
