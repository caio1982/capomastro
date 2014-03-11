from django.db import models

from jenkinsapi.jenkins import Jenkins


class JenkinsServer(models.Model):

    name = models.CharField(max_length=255, unique=True)
    url = models.CharField(max_length=255, unique=True)
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    remote_addr = models.CharField(max_length=255)

    def __str__(self):
        return "%s (%s)" % (self.name, self.url)

    def get_client(self):
        """
        Returns a configured jenkinsapi Jenkins client.
        """
        return Jenkins(
            self.url, username=self.username, password=self.password)


class Job(models.Model):

    server = models.ForeignKey(JenkinsServer)
    name = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name


class Build(models.Model):

    job = models.ForeignKey(Job)
    build_id = models.CharField(max_length=255)
    number = models.IntegerField()
    duration = models.IntegerField(null=True)
    url = models.CharField(max_length=255)
    phase = models.CharField(max_length=25) # FINISHED, STARTED, COMPLETED
    result = models.CharField(max_length=255)

    class Meta:
        ordering = ["-number"]

    def __str__(self):
        return self.build_id


class Artifact(models.Model):

    build = models.ForeignKey(Build)
    filename = models.CharField(max_length=255)
    url = models.CharField(max_length=255)