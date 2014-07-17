from django.test import TestCase

from httmock import HTTMock
from jenkinsapi.jenkins import Jenkins

from jenkins.models import Build, JobType
from .helpers import mock_url
from .factories import (
    BuildFactory, JenkinsServerFactory, JobTypeWithParamsFactory)


class JenkinsServerTest(TestCase):

    def test_get_client(self):
        """
        JenkinsServer.get_client should return a Jenkins client configured
        appropriately.
        """
        server = JenkinsServerFactory.create()

        mock_request = mock_url(
            r"\/api\/python$", "fixture1")
        with HTTMock(mock_request):
            client = server.get_client()
        self.assertIsInstance(client, Jenkins)


class BuildTest(TestCase):

    def test_ordering(self):
        """Builds should be ordered in reverse build order by default."""
        builds = BuildFactory.create_batch(5)
        build_numbers = sorted([x.number for x in builds], reverse=True)

        self.assertEqual(
            build_numbers,
            list(Build.objects.all().values_list("number", flat=True)))

    def test_phase_names(self):
        """
        The names of the phases vary depending on the version of the
        Notification plugin, so we need to define the authoritative names in
        capomastro.
        """
        self.assertEquals(Build.STARTED, 'STARTED')
        self.assertEquals(Build.COMPLETED, 'COMPLETED')
        self.assertEquals(Build.FINALIZED, 'FINALIZED')

    def test_console_log_summary(self):
        """
        Builds should have long console logs shortened to display the last n
        lines (where n is defined in CONSOLE_TAIL_LINES).
        """
        build = BuildFactory.create()

        # Check that an empty log is handled
        self.assertEquals(build.console_log, None)
        self.assertEquals(build.console_log_summary, None)

        # Create a short console log (less lines than CONSOLE_TAIL_LINES)
        short_log = "This is a single line\n".join(
            ["" for x in range(Build.CONSOLE_TAIL_LINES - 5)])
        build.console_log = short_log
        self.assertEquals(build.console_log_summary + "\n", short_log)

        # Create a longer console log (greater than CONSOLE_TAIL_LINES lines).
        long_log = "This is a single line\n".join(
            ["" for x in range(Build.CONSOLE_TAIL_LINES * 3)])
        build.console_log = long_log
        self.assertEquals(len(build.console_log_summary.splitlines()),
                          Build.CONSOLE_TAIL_LINES)


class JobTypeTest(TestCase):

    def test_instantiation(self):
        """We can create JobTypes."""
        JobType.objects.create(
            name="my-test", config_xml="testing xml")

    def test_get_parameters(self):
        """
        JobType.get_parameters should use the parameter parsing to fetch the
        correct parameters.
        """
        job_type = JobTypeWithParamsFactory.create()
        parameters = job_type.get_parameters()
        self.assertEqual(
            ["BUILD_ID", "BRANCH_TO_CHECKOUT"],
            [x["name"] for x in parameters])
