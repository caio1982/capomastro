import logging

from django.utils import timezone

from celery.utils.log import get_task_logger
from celery import shared_task

from projects.helpers import build_project
from projects.models import ProjectBuildDependency
from jenkins.models import Build

logger = get_task_logger(__name__)


def get_projectbuild_dependency_for_build(build):
    """
    Returns the ProjectBuildDependency associated with this particular Build if
    any, by looking for the build_id in the list of dependencies for this
    build_id.

    Returns None if no ProjectBuildDependency found.
    """
    if build.build_id:
        return ProjectBuildDependency.objects.filter(
            dependency__job=build.job,
            projectbuild__build_key=build.build_id).first()


@shared_task
def process_build_dependencies(build_pk):
    """
    Post build-notification handling.
    """
    build = Build.objects.get(pk=build_pk)
    update_autotracked_dependencies(build)
    update_projectbuilds(build)
    create_projectbuilds_for_autotracking(build)
    return build_pk


def update_autotracked_dependencies(build):
    """
    Find projects that use the dependency associated with this build, and if
    they're auto-tracked, update the "current_build" to be this new build.
    """
    if build.job.dependency_set.exists():
        for dependency in build.job.dependency_set.all():
            for project_dependency in dependency.projectdependency_set.filter(
                    auto_track=True):
                project_dependency.current_build = build
                project_dependency.save()


def update_projectbuilds(build):
    """
    If this build was for a ProjectBuild, i.e. if the build's build_id matches
    a ProjectBuildDependency for the build job, then we need to update the
    state of the ProjectBuild.
    """
    dependency = get_projectbuild_dependency_for_build(build)
    if dependency:
        dependency.build = build
        dependency.save()
        projectbuild = dependency.projectbuild

        build_statuses = ProjectBuildDependency.objects.filter(
            projectbuild=dependency.projectbuild).values(
            "build__status", "build__phase")

        statuses = set([x["build__status"] for x in build_statuses])
        phases = set([x["build__phase"] for x in build_statuses])
        updated = False
        if len(statuses) == 1:
            projectbuild.status = list(statuses)[0]
            updated = True
        if len(phases) == 1:
            projectbuild.phase = list(phases)[0]
            if projectbuild.phase == Build.FINALIZED:
                projectbuild.ended_at = timezone.now()
                projectbuild.save()
        elif updated:
            projectbuild.save()


def create_projectbuilds_for_autotracking(build):
    """
    If we have have projects that are autotracking the dependency associated
    with this build, then we should create project builds for them.
    """
    logging.debug("Autocreating projectbuilds for build %s", build)
    build_dependency = get_projectbuild_dependency_for_build(build)
    # At this point, we need to identify Projects which have this
    # dependency and create ProjectBuilds for them.
    for dependency in build.job.dependency_set.all():
        logging.debug("Processing dependency %s", dependency)
        for project_dependency in dependency.projectdependency_set.filter(
                auto_track=True):
            logging.debug("Processing %s", project_dependency)
            if (build_dependency is not None and
                    build_dependency.projectbuild.project ==
                        project_dependency.project):
                continue
            else:
                process_project_dependency(
                    build, dependency, project_dependency)


def process_project_dependency(build, dependency, project_dependency):
    """
    Create a new projectbuild, without building the dependencies, and associate
    the projectbuild_dependency for the dependency associated with the build
    we're processing.
    """
    logging.debug("  autocreating projectbuild")
    # We have a Project with a an auto-tracked element.
    projectbuild = build_project(
        project_dependency.project, dependencies=None,
        queue_build=False, automated=True)
    projectbuild_dependency = projectbuild.dependencies.get(
        dependency=dependency)
    projectbuild_dependency.build = build
    projectbuild_dependency.save()
