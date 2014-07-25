from django import forms

from jenkins.models import JenkinsServer, JobType
from projects.models import (
    Project, Dependency, ProjectDependency)
from jenkins.helpers import create_job
from jenkins.tasks import push_job_to_jenkins


class ProjectForm(forms.ModelForm):

    auto_track = forms.BooleanField(
        help_text="Auto track dependencies", required=False)

    class Meta:
        model = Project

    def save(self, commit=True):
        project = super(ProjectForm, self).save(commit=False)
        project.save()

        requested_dependencies = set(self.cleaned_data["dependencies"])
        current_dependencies = set(
            [x.dependency for x in ProjectDependency.objects.filter(
                project=project)])

        dependencies_to_remove = current_dependencies - requested_dependencies
        dependencies_to_add = requested_dependencies - current_dependencies

        for dependency in dependencies_to_remove:
            ProjectDependency.objects.get(
                project=project, dependency=dependency).delete()

        auto_track = self.data.get("auto_track", False)
        # Set remaining dependencies for this project to use the auto_track
        # value requested.
        ProjectDependency.objects.filter(
            project=project).update(auto_track=auto_track)

        # TODO: This probably shouldn't use the get_current_build if
        # auto_track=False
        for dependency in dependencies_to_add:
            ProjectDependency.objects.create(
                project=project, dependency=dependency,
                auto_track=auto_track,
                current_build=dependency.get_current_build())
        return project


class DependencyCreateForm(forms.ModelForm):

    jobtype = forms.ModelChoiceField(
        queryset=JobType.objects, required=True, label="Job type",
        help_text="Select a job type to use.")
    server = forms.ModelChoiceField(
        queryset=JenkinsServer.objects, required=True)

    class Meta:
        model = Dependency
        exclude = ["job"]

    def save(self, commit=True):
        dependency = super(DependencyCreateForm, self).save(commit=commit)
        job = create_job(
            self.cleaned_data["jobtype"], self.cleaned_data["server"])
        push_job_to_jenkins.delay(job.pk)
        dependency.job = job
        dependency.save()
        return dependency


class ProjectBuildForm(forms.Form):

    dependencies = forms.ModelMultipleChoiceField(
        Dependency.objects, required=True, widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Must select at least one dependency."})
    project = forms.ModelChoiceField(
        Project.objects, required=True, widget=forms.HiddenInput)
