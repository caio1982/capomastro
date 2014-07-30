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

    If dependencies is a list of ProjectDependencies, then these will be built,
    and the rest of the project's dependencies will not.

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

    previous_build = project.get_current_projectbuild()
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
        remaining_builds = list(dependencies_not_to_build) + list(
            dependencies_to_build)
    else:
        remaining_builds = dependencies_not_to_build

    for dependency in remaining_builds:
        last_known_build = get_last_build_for_dependency(
            dependency, previous_build)
        kwargs = {"projectbuild": build,
                  "dependency": dependency.dependency,
                  "build": last_known_build}
        ProjectBuildDependency.objects.create(**kwargs)
    return build


def get_last_build_for_dependency(dependency, previous_build=None):
    """
    Return the last known build for the provided ProjectDependency dependency,
    which is defined as the current build associated with itself if it's not
    auto-tracked, or the most recent build for auto-tracked cases.
    """
    if dependency.auto_track:
        if previous_build:
            return previous_build.build_dependencies.filter(
                projectdependency=dependency).first()
    return dependency.current_build
