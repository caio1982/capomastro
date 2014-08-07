from django.core.urlresolvers import reverse
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.contrib.auth.models import User

from jenkinsapi.jenkins import Jenkins
from jenkins.utils import parse_parameters_from_job
from jenkins import fields


@python_2_unicode_compatible
class JenkinsServer(models.Model):

    name = models.CharField(max_length=255, unique=True)
    url = models.CharField(max_length=255, unique=True)
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)

    def __str__(self):
        return "%s (%s)" % (self.name, self.url)

    def get_client(self):
        """
        Returns a configured jenkinsapi Jenkins client.
        """
        return Jenkins(
            self.url, username=self.username, password=self.password)


@python_2_unicode_compatible
class JobType(models.Model):
    """
    Used as a model for creating new Jenkins jobs.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    config_xml = models.TextField()

    def __str__(self):
        return self.name

    def get_parameters(self):
        """
        Parse the config_xml and extract the parameters.
        """
        return parse_parameters_from_job(self.config_xml)


@python_2_unicode_compatible
class Job(models.Model):

    server = models.ForeignKey(JenkinsServer)
    jobtype = models.ForeignKey(JobType)
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = "server", "name"

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class Build(models.Model):
    # Define the phase names
    STARTED = 'STARTED'
    COMPLETED = 'COMPLETED'
    FINALIZED = 'FINALIZED'

    # Console log tail size
    CONSOLE_TAIL_LINES = 20

    job = models.ForeignKey(Job)
    build_id = models.CharField(max_length=255)
    number = models.IntegerField()
    duration = models.IntegerField(null=True)
    url = models.CharField(max_length=255)
    phase = models.CharField(max_length=25)  # FINALIZED, STARTED, COMPLETED
    status = models.CharField(max_length=255)
    console_log = models.TextField(blank=True, null=True, editable=False)
    parameters = fields.JSONField(blank=True, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    requested_by = models.ForeignKey(User, null=True, editable=False, blank=True)

    class Meta:
        ordering = ["-number"]

    def __str__(self):
        return self.build_id or "%s %s" % (self.job, self.number)

    @staticmethod
    def translate_build_phase(phase):
        """
        Jenkins notifications changed the phase from FINISHED to FINALIZED.
        """
        if phase == "FINISHED":
            return Build.FINALIZED
        return phase

    @property
    def console_log_summary(self):
        """
        The console log can get long for some builds and increase the time it
        takes to render the page. This summary provides a truncated version of
        the log.
        """
        if not self.console_log:
            return self.console_log

        log = self.console_log.splitlines()[-self.CONSOLE_TAIL_LINES:]
        return "\n".join(log)

    def get_absolute_url(self):
        """
        Return the URL for the ProjectBuild.
        """
        return reverse("build_detail", kwargs={"pk": self.pk})


@python_2_unicode_compatible
class Artifact(models.Model):

    build = models.ForeignKey(Build)
    filename = models.CharField(max_length=255)
    url = models.CharField(max_length=255)

    def __str__(self):
        return "%s for %s" % (self.filename, self.build)
