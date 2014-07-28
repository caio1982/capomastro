import logging

from django.utils import timezone

from celery import shared_task, chain

from archives.helpers import get_default_archive
from archives.models import ArchiveArtifact
from jenkins.models import Build


def link_to_current_if_required(projectbuild, item, transport):
    """
    If this build is a projectbuild build, then we should link the current
    projectbuild to the "current" directory.

    If this build is not a projectbuild, it's safe to link the current directory
    after this build.
    """
    if projectbuild:
        if projectbuild.phase == Build.FINALIZED:
            transport.link_to_current(item.archived_path)
    else:
        transport.link_to_current(item.archived_path)


@shared_task
def archive_artifact_from_jenkins(archiveartifact_pk):
    """
    Schedule the transfer of the file in the artifact to the specified archive.
    """
    item = ArchiveArtifact.objects.get(pk=archiveartifact_pk)
    logging.info("Archiving %s in archive %s", item, item.archive)

    transport = item.archive.get_transport()
    artifact = item.artifact

    projectbuild = (item.projectbuild_dependency and
                    item.projectbuild_dependency.projectbuild)

    server = artifact.build.job.server
    transport.start()
    logging.info("  %s -> %s", artifact.url, item.archived_path)
    size = transport.archive_url(
        item.artifact.url, item.archived_path,
        username=server.username, password=server.password)

    link_to_current_if_required(projectbuild, item, transport)

    transport.end()
    item.archived_at = timezone.now()
    item.archived_size = size
    item.save()
    logging.info("  archived at %s", item.archived_at)


@shared_task
def link_artifact_in_archive(source_pk, destination_pk):
    """
    This task uses the underlying transport to link the source archiveartifact
    to the destination archiveartifact without duplicating the file.
    """
    destination = ArchiveArtifact.objects.get(pk=destination_pk)
    source = ArchiveArtifact.objects.get(pk=source_pk)

    projectbuild = (destination.projectbuild_dependency and
                    destination.projectbuild_dependency.projectbuild)
    logging.info("Archiving %s in archive %s", destination, source.archive)

    transport = source.archive.get_transport()
    transport.start()
    logging.info("  %s -> %s", source.archived_path, destination.archived_path)

    transport.link_filename_to_filename(
        source.archived_path, destination.archived_path)

    link_to_current_if_required(projectbuild, destination, transport)

    transport.end()
    destination.archived_at = timezone.now()
    destination.archived_size = source.archived_size
    destination.save()
    logging.info("  archived at %s", destination.archived_at)
    destination.save()


# TODO Workout some sort of decorator so these functions don't have to return
# build_pk in the chain
@shared_task
def process_build_artifacts(build_pk):
    """
    This task should be triggered after we've imported the artifacts from
    Jenkins for a build.
    """
    build = Build.objects.get(pk=build_pk)
    logging.info(
        "Processing build artifacts from build %s %d", build, build.number)
    archive = get_default_archive()
    if archive:
        items = archive.add_build(build)
        logging.info("Archiving %s", items)
        for artifact, files in items.items():
            first, rest = files[0], files[1:]
            chain(
                archive_artifact_from_jenkins.si(first.pk),
                *[link_artifact_in_archive.si(first.pk, item.pk) for item in
                  rest]).apply()
    else:
        logging.info("No default archiver - build not automatically archived.")
    return build_pk


@shared_task
def generate_checksums(build_pk):
    """
    This task should ask the archive transport to generate checksum files
    for each project build the specified build has caused.
    """
    build = Build.objects.get(pk=build_pk)
    archive = get_default_archive()
    transport = archive.get_transport()
    archived_artifacts = archive.get_archived_artifacts_for_build(build)
    transport.start()
    for artifact in archived_artifacts:
        if artifact.projectbuild_dependency:
            logging.info("Generating checksums for %s" % artifact)
            transport.generate_checksums(artifact)
    transport.end()
