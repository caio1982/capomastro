from django.core.paginator import (
    Paginator, EmptyPage, PageNotAnInteger)
from django.shortcuts import get_object_or_404
from django.views.generic import (
    CreateView, ListView, DetailView, FormView, UpdateView, DeleteView)
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect

from braces.views import (
    LoginRequiredMixin, PermissionRequiredMixin, FormValidMessageMixin)
from archives.models import ArchiveArtifact

from jenkins.models import Build
from jenkins.tasks import delete_job_from_jenkins
from jenkins.utils import parse_parameters_from_job
from projects.models import (
    Project, Dependency, ProjectDependency, ProjectBuild,
    ProjectBuildDependency)
from projects.forms import (
    ProjectForm, DependencyCreateForm, ProjectBuildForm)
from projects.helpers import build_project, build_dependency
from projects.utils import get_build_table_for_project
from archives.helpers import get_default_archive


class ProjectCreateView(
    LoginRequiredMixin, PermissionRequiredMixin, FormValidMessageMixin,
        CreateView):

    raise_exception = True
    permission_required = "projects.add_project"
    form_valid_message = "Project created"
    model = Project
    form_class = ProjectForm

    def get_success_url(self):
        return reverse("project_detail", kwargs={"pk": self.object.pk})

    def get_initial(self):
        """
        We need to default the auto_track to True because we add it to the form
        in the form definition.
        """
        initial = super(ProjectCreateView, self).get_initial()
        initial["auto_track"] = True
        return initial


class ProjectListView(LoginRequiredMixin, ListView):

    model = Project


class ProjectUpdateView(
    LoginRequiredMixin, PermissionRequiredMixin, FormValidMessageMixin,
        UpdateView):

    raise_exception = True
    permission_required = "projects.change_project"
    form_valid_message = "Project updated"
    model = Project
    form_class = ProjectForm

    def get_success_url(self):
        return reverse("project_detail", kwargs={"pk": self.object.pk})


class InitiateProjectBuildView(LoginRequiredMixin, FormView):
    """
    Starts building a project and redirects to the newly created ProjectBuild.
    """
    form_class = ProjectBuildForm
    template_name = "projects/projectbuild_form.html"

    def get_form(self, form_class):
        """
        Returns an instance of the form to be used in this view.
        """
        project = get_object_or_404(Project, pk=self.kwargs["pk"])
        form = form_class(**self.get_form_kwargs())
        dependencies = project.dependencies
        form.fields["dependencies"].queryset = dependencies
        initial_pks = [x.pk for x in dependencies.all()]
        form.fields["dependencies"].initial = initial_pks
        form.fields["project"].initial = project
        return form

    def form_valid(self, form):
        project = form.cleaned_data["project"]
        projectbuild = build_project(
            project, user=self.request.user,
            dependencies=form.cleaned_data["dependencies"])
        messages.add_message(
            self.request, messages.INFO,
            "Build '%s' queued." % projectbuild.build_id)

        url_args = {"project_pk": project.pk, "build_pk": projectbuild.pk}
        url = reverse("project_projectbuild_detail", kwargs=url_args)
        return HttpResponseRedirect(url)


class ProjectBuildListView(LoginRequiredMixin, ListView):

    context_object_name = "projectbuilds"
    model = ProjectBuild

    def get_queryset(self):
        return ProjectBuild.objects.filter(
            project=self._get_project_from_url())

    def _get_project_from_url(self):
        return get_object_or_404(Project, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        """
        Supplement the projectbuilds with the project:
        """
        context = super(
            ProjectBuildListView, self).get_context_data(**kwargs)
        context["project"] = self._get_project_from_url()
        return context


class ProjectBuildDetailView(LoginRequiredMixin, DetailView):

    template_name = "projects/projectbuild_detail.html"

    def get_object(self):
        project_pk = self.kwargs["project_pk"]
        build_pk = self.kwargs["build_pk"]
        return get_object_or_404(
            ProjectBuild, project__pk=project_pk, pk=build_pk)

    def _get_project_from_url(self):
        return get_object_or_404(Project, pk=self.kwargs["project_pk"])

    def _get_build_from_url(self):
        project_pk = self.kwargs["project_pk"]
        build_pk = self.kwargs["build_pk"]
        return get_object_or_404(
            ProjectBuild, project__pk=project_pk, pk=build_pk)

    def _get_build_dependencies(self, projectbuild):
        return ProjectBuildDependency.objects.filter(projectbuild=projectbuild)

    def get_context_data(self, **kwargs):
        """
        Supplement the projectbuilds with the project:
        """
        context = super(
            ProjectBuildDetailView, self).get_context_data(**kwargs)
        context["project"] = self._get_project_from_url()
        context["projectbuild"] = self._get_build_from_url()
        context["dependencies"] = self._get_build_dependencies(
            context["projectbuild"])

        archive = get_default_archive()
        if archive:
            context["archived_items"] = archive.items.filter(
                projectbuild_dependency__projectbuild=context["projectbuild"])
        return context


class ProjectDetailView(LoginRequiredMixin, DetailView):

    model = Project
    context_object_name = "project"

    def get_context_data(self, **kwargs):
        """
        Supplement the project with its dependencies.
        """
        context = super(
            ProjectDetailView, self).get_context_data(**kwargs)
        context["dependencies"] = ProjectDependency.objects.filter(
            project=context["project"])
        context["projectbuilds"] = ProjectBuild.objects.filter(
            project=context["project"]).order_by("-build_id")[:5]

        items = []
        # Get the artifacts for the current project build
        current_projectbuild = context["project"].get_current_projectbuild()
        if current_projectbuild:
            # Get the archived artifacts
            archived_item_query = ArchiveArtifact.objects.filter(
                projectbuild_dependency__projectbuild=current_projectbuild)
            for archived_item in archived_item_query.all():
                    items.append(
                        self.item_from_archived_artifact(archived_item))

            # Get the unarchived artifacts
            if len(items) == 0:
                for artifact in current_projectbuild.get_current_artifacts():
                    items.append(self.item_from_artifact(artifact))
        context["current_artifacts"] = items
        return context

    @staticmethod
    def item_from_archived_artifact(archived_item):
        """
        Return an archived artifact in a standard format for display.
        """
        return {
            "build_name": "%s %s" % (archived_item.build.job,
                                     archived_item.build.number),
            "filename": archived_item.artifact.filename,
            "url": archived_item.get_url(),
            "archived": True,
        }

    @staticmethod
    def item_from_artifact(artifact):
        """
        Return an artifact in a standard format for display.
        """
        return {
            "build_name": "%s %s" % (
                artifact.build.job, artifact.build.number),
            "filename": artifact.filename,
            "url": artifact.url,
            "archived": False,
        }


class DependencyCreateView(
    LoginRequiredMixin, PermissionRequiredMixin, FormValidMessageMixin,
        CreateView):

    raise_exception = True
    permission_required = "projects.add_dependency"
    form_valid_message = "Dependency created"
    form_class = DependencyCreateForm
    model = Dependency

    def get_success_url(self):
        url_args = {"pk": self.object.pk}
        return reverse("dependency_detail", kwargs=url_args)


class DependencyListView(LoginRequiredMixin, ListView):

    context_object_name = "dependencies"
    model = Dependency


class DependencyDetailView(LoginRequiredMixin, DetailView):

    PAGINATE_BUILDS = 5
    context_object_name = "dependency"
    model = Dependency

    def paginate_builds(self, context, page):
        """
        Paginate the builds list so it returns n at a time (n is defined in
        PAGINATE_BUILDS).
        :param context: the context data
        :param page: the requested page number
        """
        builds_list = Build.objects.filter(job=context["dependency"].job)
        paginator = Paginator(builds_list, self.PAGINATE_BUILDS)

        try:
            builds = paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer, send the first page.
            builds = paginator.page(1)
        except EmptyPage:
            # If page is out of range, send the last page of results.
            builds = paginator.page(paginator.num_pages)
        return builds

    def get_context_data(self, **kwargs):
        """
        Supplement the dependency.
        """
        context = super(
            DependencyDetailView, self).get_context_data(**kwargs)

        context["builds"] = self.paginate_builds(
            context=context, page=self.request.GET.get('page'))
        context["projects"] = Project.objects.filter(
            dependencies=context["dependency"])
        if context["dependency"].is_building:
            messages.add_message(
                self.request, messages.INFO,
                "Dependency currently building")
        return context

    def post(self, request, pk):
        """
        Queue a build of this Dependency.
        """
        dependency = get_object_or_404(Dependency, pk=pk)
        build_dependency(dependency, user=request.user)
        messages.add_message(
            self.request, messages.INFO,
            "Build for '%s' queued." % dependency.name)
        url = reverse("dependency_detail", kwargs={"pk": dependency.pk})
        return HttpResponseRedirect(url)


class ProjectDependenciesView(LoginRequiredMixin, DetailView):

    model = Project
    context_object_name = "project"
    template_name = "projects/project_dependencies.html"

    def _get_builds_for_dependency(self, projectdependency):
        """
        Return the builds for a project dependency.
        """
        return Build.objects.filter(job=projectdependency.dependency.job)

    def get_context_data(self, **kwargs):
        """
        Supplement the project with its dependencies.
        """
        context = super(
            ProjectDependenciesView, self).get_context_data(**kwargs)
        header, table = get_build_table_for_project(context["project"])
        context["builds_header"] = header
        context["builds_table"] = table
        return context


class DependencyUpdateView(
    LoginRequiredMixin, PermissionRequiredMixin, FormValidMessageMixin,
        UpdateView):

    permission_required = "projects.change_dependency"
    form_valid_message = "Dependency updated"
    model = Dependency
    fields = ["name", "description", "parameters"]

    def get_success_url(self):
        return reverse("dependency_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        """
        Supplement the dependency.
        """
        context = super(
            DependencyUpdateView, self).get_context_data(**kwargs)
        params = [x for x in
                  parse_parameters_from_job(self.object.job.jobtype.config_xml)
                  if x["name"] != "BUILD_ID"]
        context["parameters"] = params
        return context


class DependencyDeleteView(
        LoginRequiredMixin, PermissionRequiredMixin, DeleteView):

    permission_required = "projects.delete_dependency"
    model = Dependency

    def delete(self, request, *args, **kwargs):
        response = super(DependencyDeleteView, self).delete(
            request, *args, **kwargs)
        messages.add_message(
            self.request, messages.INFO,
            "Dependency '%s' deleted." % self.object.name)
        delete_job_from_jenkins.delay(self.object.job.pk)
        return response

    def get_success_url(self):
        return reverse("home")

    def get_context_data(self, **kwargs):
        """
        Supplement the dependency.
        """
        context = super(
            DependencyDeleteView, self).get_context_data(**kwargs)
        context["projects"] = Project.objects.filter(
            dependencies=context["dependency"])
        if context["dependency"].is_building:
            messages.add_message(
                self.request, messages.INFO,
                "Dependency currently building")
        return context


__all__ = [
    "ProjectCreateView", "ProjectListView", "ProjectDetailView",
    "DependencyCreateView", "InitiateProjectBuildView", "ProjectBuildListView",
    "ProjectBuildDetailView", "DependencyListView", "DependencyDetailView",
    "ProjectUpdateView", "ProjectDependenciesView", "DependencyUpdateView",
    "DependencyDeleteView"
]
