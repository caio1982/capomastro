import uuid

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.core.exceptions import ValidationError

from jenkins.models import Job, Build, Artifact


def validate_parameters(value):
    try:
        split_parameters(value)
    except ValueError:
        raise ValidationError(
            "Invalid parameters entered.  Must be separated by newline.")


@python_2_unicode_compatible
class Dependency(models.Model):

    name = models.CharField(max_length=255, unique=True)
    job = models.ForeignKey(Job, null=True)
    description = models.TextField(null=True, blank=True)
    parameters = models.TextField(
        null=True, blank=True, validators=[validate_parameters])

    class Meta:
        verbose_name_plural = "dependencies"

    def __str__(self):
        return self.name

    def get_current_build(self):
        """
        Return the most recent build
        """
        if self.job is not None:
            finished_builds = self.job.build_set.filter(phase=Build.FINALIZED)
            if finished_builds.count() > 0:
                return finished_builds.order_by("-number")[0]

    def get_build_parameters(self):
        """
        Return the parameters property parsed into a dictionary of "build"
        parameters.

        If we have no parameters, we should get None back.
        """
        try:
            return split_parameters(self.parameters)
        except ValueError:
            return

    @property
    def is_building(self):
        """
        Returns True if we believe this dependency is currently being built
        on a server.

        TODO: What happens if we never get the "FINALIZED" / "COMPLETED"
        notifications? Status gets left as "UNKNOWN"
        """
        return Build.objects.filter(
            job=self.job, phase=Build.STARTED).exists()


@python_2_unicode_compatible
class ProjectDependency(models.Model):
    """
    Represents the build of a dependency used by a project.

    e.g. Project X can use build 20 of dependency Y while
         Project Z is using build 23.

         So, this is the specific "tag" version of the
         dependency that's used by this project.

         We can have a UI that shows what the current version is
         and the current version, and allow promoting to a newer version.
    """
    dependency = models.ForeignKey(Dependency)
    project = models.ForeignKey("Project")
    auto_track = models.BooleanField(default=True)
    current_build = models.ForeignKey(Build, null=True, editable=False)

    class Meta:
        verbose_name_plural = "project dependencies"

    def __str__(self):
        return "{0} dependency for {1} {2}".format(
            self.dependency, self.project, self.auto_track)


@python_2_unicode_compatible
class Project(models.Model):

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    dependencies = models.ManyToManyField(
        Dependency, through=ProjectDependency)

    def get_current_artifacts(self):
        """
        Returns a QuerySet of Artifact objects representing the Artifacts
        associated with the project dependencies at their current dependency
        level.
        """
        current_builds = []
        for dependency in ProjectDependency.objects.filter(project=self):
            current_builds.append(dependency.current_build)
        return Artifact.objects.filter(build__in=current_builds)

    def get_current_projectbuild(self):
        """
        Return the most recent FINALIZED ProjectBuild for this project.
        """
        return ProjectBuild.objects.filter(project=self,
            phase=Build.FINALIZED).order_by("-ended_at").first()

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class ProjectBuildDependency(models.Model):
    """
    Represents one of the dependencies of a particular Project Build.
    """
    projectbuild = models.ForeignKey(
        "ProjectBuild", related_name="dependencies")
    build = models.ForeignKey(
        Build, blank=True, null=True,
        related_name="projectbuild_dependencies")
    dependency = models.ForeignKey(Dependency)

    class Meta:
        verbose_name_plural = "project build dependencies"

    def __str__(self):
        return "Build of {0} for {1}".format(
            self.dependency.name, self.projectbuild.build_id)


def generate_build_key():
    """Generate a unique key for builds."""
    return uuid.uuid4().get_hex()


@python_2_unicode_compatible
class ProjectBuild(models.Model):
    """Represents a requested build of a Project."""

    project = models.ForeignKey(Project)
    requested_by = models.ForeignKey(User, null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=10, default="UNKNOWN")
    phase = models.CharField(max_length=25, default="UNKNOWN")
    build_id = models.CharField(max_length=20)
    archived = models.DateTimeField(null=True, blank=True)
    build_key = models.CharField(max_length=32, default=generate_build_key)

    build_dependencies = models.ManyToManyField(
        Build, through=ProjectBuildDependency)

    def __str__(self):
        return "%s %s" % (self.project.name, self.build_key)

    def get_current_artifacts(self):
        """
        Returns a QuerySet of Artifact objects representing the Artifacts
        associated with the builds of the project dependencies for this
        project build.
        """
        return Artifact.objects.filter(build__build_id=self.build_key)

    @property
    def can_be_archived(self):
        """
        Returns True if the requirements for archiving this ProjectBuild are
        met.
        """
        return (
            self.phase == Build.FINALIZED
            and not self.archived
            and self.get_current_artifacts().exists())

    def save(self, **kwargs):
        if not self.pk:
            self.build_id = generate_projectbuild_id(self)

        super(ProjectBuild, self).save(**kwargs)


def generate_projectbuild_id(projectbuild):
    """
    Generates a daily-unique id for a given project.

    TODO: Should this drop the ".0" when there's no previous builds?
    """
    # This is a possible race condition
    today = timezone.now()

    day_start = today.replace(hour=0, minute=0, second=0)
    day_end = today.replace(hour=23, minute=59, second=59)
    filters = {"requested_at__gt": day_start,
               "requested_at__lte": day_end,
               "project": projectbuild.project}
    today_count = ProjectBuild.objects.filter(**filters).count()
    return today.strftime("%%Y%%m%%d.%d" % today_count)


def split_parameters(parameters):
    """
    Splits the parameters string into a dictionary of parameters.
    """
    if not parameters:
        return
    build_parameters = {}
    keyvalues = [x for x in parameters.split("\n") if x.strip()]
    for keyvalue in keyvalues:
        key, value = keyvalue.split("=")
        build_parameters[key.strip()] = value.strip()
    return build_parameters
