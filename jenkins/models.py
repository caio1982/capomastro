from django.db import models
from django.utils.encoding import python_2_unicode_compatible

from jenkinsapi.jenkins import Jenkins
from jenkins.utils import parse_parameters_from_job


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

    job = models.ForeignKey(Job)
    build_id = models.CharField(max_length=255)
    number = models.IntegerField()
    duration = models.IntegerField(null=True)
    url = models.CharField(max_length=255)
    phase = models.CharField(max_length=25)  # FINISHED, STARTED, COMPLETED
    status = models.CharField(max_length=255)
    console_log = models.TextField(blank=True, null=True, editable=False)

    class Meta:
        ordering = ["-number"]

    def __str__(self):
        return self.build_id


@python_2_unicode_compatible
class Artifact(models.Model):

    build = models.ForeignKey(Build)
    filename = models.CharField(max_length=255)
    url = models.CharField(max_length=255)

    def __str__(self):
        return "%s for %s" % (self.filename, self.build)
