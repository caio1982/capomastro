import factory

from projects.models import Project, Dependency, DependencyType

class ProjectFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Project

    name = factory.Sequence(lambda n: 'Project %s' % n)


class DependencyTypeFactory(factory.DjangoModelFactory):
    FACTORY_FOR = DependencyType

    name = factory.Sequence(lambda n: 'type%s' % n)


class DependencyFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Dependency

    dependency_type = factory.SubFactory(DependencyTypeFactory)
    name = factory.Sequence(lambda n: 'Dependency %s' % n)
