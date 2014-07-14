from jenkins.tasks import build_job
from jenkins.models import Build
from projects.models import ProjectDependency


def build_dependency(dependency, build_id=None, user=None):
    """
    Queues a build of the job associated with the depenency along with
    any parameters that might be needed.
    """
    build_parameters = dependency.get_build_parameters()
    kwargs = {}
    if build_parameters:
        kwargs["params"] = build_parameters
    if build_id:
        kwargs["build_id"] = build_id
    if user:
        kwargs["user"] = user.username
    build_job.delay(
        dependency.job.pk, **kwargs)


def build_project(project, user=None, dependencies=None, **kwargs):
    """
    Given a build, schedule building each of its dependencies.

    if queue_build parameter is False, then don't actually do the builds, just
    create the ProjectBuildDependencies for the project.

    if automated is True, then we are handling an automatically created
    ProjectBuild, and we should create ProjectBuildDependencies with builds
    for all dependencies.
    """
    queue_build = kwargs.pop("queue_build", True)
    dependencies = dependencies and dependencies or []
    from projects.models import ProjectBuild, ProjectBuildDependency

    automated = kwargs.pop("automated", False)

    options = {"project": project, "requested_by": user}
    if automated:
        options["phase"] = Build.FINALIZED
    build = ProjectBuild.objects.create(**options)

    if dependencies:
        filter_args = {"dependency__in": dependencies}
    else:
        filter_args = {}

    dependencies_to_build = ProjectDependency.objects.filter(
        project=project, **filter_args)
    dependencies_not_to_build = ProjectDependency.objects.filter(
        project=project).exclude(pk__in=dependencies_to_build)

    if not automated:
        for dependency in dependencies_to_build.order_by(
                "dependency__job__pk"):
            kwargs = {"projectbuild": build,
                      "dependency": dependency.dependency}
            ProjectBuildDependency.objects.create(**kwargs)
            if queue_build:
                build_dependency(
                    dependency.dependency, build_id=build.build_key, user=user)

    # If it's automated, then we create a ProjectBuildDependency for each
    # dependency of the project and prepopulate it with the last known build.
    if automated:
        dependencies_not_to_build = dependencies_to_build

    for dependency in dependencies_not_to_build:
        kwargs = {"projectbuild": build,
                  "dependency": dependency.dependency,
                  "build": dependency.current_build}
        ProjectBuildDependency.objects.create(**kwargs)
    return build
