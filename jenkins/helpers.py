import logging

from django.conf import settings
from celery import chain

from jenkins.models import Job
from jenkins.utils import generate_job_name
from jenkins.tasks import import_build_for_job


def create_job(jobtype, server):
    """
    Create a job in the given Jenkins Server.
    """
    name = generate_job_name(jobtype)
    job = Job.objects.create(jobtype=jobtype, server=server, name=name)
    return job


def import_builds_for_job(job_pk):
    """
    Import all Builds for a job using the job_pk.

    TODO: Add testing - only used by command-line tool just now.
    """
    job = Job.objects.get(pk=job_pk)

    logging.info("Located job %s\n" % job)

    client = job.server.get_client()

    logging.info("Using server at %s\n" % job.server.url)

    jenkins_job = client.get_job(job.name)

    good_build_numbers = list(jenkins_job.get_build_ids())
    logging.info("%s\n" % good_build_numbers)

    for build_number in good_build_numbers:
        import_build_for_job(job.pk, build_number)


def postprocess_build(build):
    """
    Queues importing the specified build from Jenkins including details of the
    artifacts etc.

    When a build completes, execute any tasks that should be executed post
    build.
    """
    post_build_tasks = getattr(settings, "POST_BUILD_TASKS", [])
    additional_tasks = [x.s() for x in post_build_tasks]
    return chain(
        import_build_for_job.s(build.pk), *additional_tasks).apply_async()

