import json

from django.db import models


class JSONField(models.Field):
    """
    Simple field that stores in JSON format.
    """
    __metaclass__ = models.SubfieldBase

    def to_python(self, value):
        if isinstance(value, dict):
            return value
        else:
            if not value:
                return value
        return json.loads(value)

    def get_db_prep_save(self, value, connection):
        if value is not None and not isinstance(value, basestring):
            value = json.dumps(value)
        return value

    def get_internal_type(self):
        return "TextField"

    def get_db_prep_lookup(self, lookup_type, value):
        if lookup_type == "exact":
            value = self.get_db_prep_save(value)
            return super(JSONField, self).get_db_prep_lookup(
                lookup_type, value)
        else:
            raise TypeError("Lookup type %s is not supported." % lookup_type)
