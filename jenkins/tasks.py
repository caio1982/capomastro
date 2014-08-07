from django.contrib.auth.models import User

from celery.utils.log import get_task_logger
from celery import shared_task

from jenkins.models import Job, Build, Artifact
from jenkins.utils import get_job_xml_for_upload

logger = get_task_logger(__name__)


@shared_task
def build_job(job_pk, build_id=None, params=None, user=None):
    """
    Request building Job.
    """
    # TODO: If a job is already queued, then this can throw
    # WillNotBuild: <jenkinsapi.job.Job job> is already queued
    job = Job.objects.get(pk=job_pk)
    client = job.server.get_client()
    if params is None:
        params = {}
    if build_id is not None:
        params["BUILD_ID"] = build_id
    if user is not None:
        params["REQUESTOR"] = user
    client.build_job(job.name, params=params)


@shared_task
def push_job_to_jenkins(job_pk):
    """
    Create or update a job in the server with the config.
    """
    job = Job.objects.get(pk=job_pk)
    xml = get_job_xml_for_upload(job, job.server)
    client = job.server.get_client()

    if client.has_job(job.name):
        job = client.get_job(job.name)
        job.update_config(xml)
    else:
        client.create_job(job.name, xml)


def extract_requestor_from_params(params):
    """
    Return the requesting user or None if we couldn't find a REQUESTOR in the
    build parameters.
    """
    for param in params:
        if param["name"] == "REQUESTOR":
            try:
                return User.objects.get(username=param["value"])
            except User.DoesNotExist:
                logger.info("Unknown REQUESTOR %s", param["value"])
                return


@shared_task
def import_build_for_job(build_pk):
    """
    Import a build for a job.
    """
    build = Build.objects.get(pk=build_pk)
    logger.info("Located job %s\n" % build.job)

    client = build.job.server.get_client()
    logger.info("Using server at %s\n" % build.job.server.url)

    jenkins_job = client.get_job(build.job.name)
    build_result = jenkins_job.get_build(build.number)

    # TODO: Shouldn't access _data here.
    build_details = {
        "status": build_result.get_status(),
        # TODO: What should we do with this ID we get from Jenkins?
        # Discard? or only set it if we don't have one?
        # "build_id": build_result._data["id"],
        "duration": build_result._data["duration"],
        "url": build_result.get_result_url(),
        "console_log": build_result.get_console(),
        "parameters": build_result.get_actions()["parameters"],
    }
    requestor = extract_requestor_from_params(build_details["parameters"])
    build_details["requested_by"] = requestor
    logger.info("Processing build details for %s #%d" % (
        build.job, build.number))
    Build.objects.filter(
        job=build.job, number=build.number).update(**build_details)
    build = Build.objects.get(job=build.job, number=build.number)
    for artifact in build_result.get_artifacts():
        artifact_details = {
            "filename": artifact.filename,
            "url": artifact.url,
            "build": build
        }
        logger.info("Importing artifact %s", artifact_details)
        Artifact.objects.create(**artifact_details)
    return build_pk


@shared_task
def delete_job_from_jenkins(job_pk):
    """
    Deletes a job from its Jenkins server.
    """
    job = Job.objects.get(pk=job_pk)
    client = job.server.get_client()

    return client.delete_job(job.name)
