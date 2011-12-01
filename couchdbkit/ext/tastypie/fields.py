from tastypie.bundle import Bundle
from tastypie.exceptions import ApiFieldError
from tastypie.fields import ListField, DictField

from .resources import DocumentResource


def _get_fields(obj):
    """Create fields for the couch object"""
    schema = obj.schema()
    final_fields = {}

    for f in schema._properties.values():
        kwargs = {
            'attribute': f.name,
            'blank': not f.required,
            'default': f.default,
        }

        api_field_class = DocumentResource.api_field_from_couch_field(f)
        final_fields[f.name] = api_field_class(**kwargs)
        final_fields[f.name].instance_name = f.name
    return final_fields


class SchemaListField(ListField):
    def dehydrate(self, bundle):
        if self.attribute is not None:
            obj = getattr(bundle.obj, self.attribute)
            final_fields = _get_fields(obj)
            schema = obj.schema()

            # Run through the list and dehydrate each item
            obj_data = []
            for item in obj:
                obj_bundle = Bundle(item)
                for field_name, field_object in final_fields.items():
                    obj_bundle.data[field_name] = field_object.dehydrate(obj_bundle)
                obj_data.append(obj_bundle.data)

            return self.convert(obj_data)

        if self.has_default():
            return self.convert(self.default)
        else:
            return None

    def hydrate(self, bundle):
        if self.readonly:
            return None

        # Check the bundle for data
        if self.instance_name not in bundle.data:
            if self.blank:
                return None
            elif self.attribute and getattr(bundle.obj, self.attribute, None):
                return getattr(bundle.obj, self.attribute)
            elif self.instance_name and hasattr(bundle.obj, self.instance_name):
                return getattr(bundle.obj, self.instance_name)
            elif self.has_default():
                if callable(self._default):
                    return self._default()

                return self._default
            elif self.null:
                return None
            else:
                raise ApiFieldError("The '%s' field has no data and doesn't allow a default or null value." % self.instance_name)

        obj = getattr(bundle.obj, self.attribute)
        schema = obj.schema()

        del obj[:]
        final_fields = _get_fields(obj)

        # Run through the list and hydrate each item
        obj_data = bundle.data.get(self.attribute, [])
        for data in obj_data:
            obj_bundle = Bundle(obj.schema(), data)
            for field_name, field_object in final_fields.items():
                setattr(obj_bundle.obj, field_name, field_object.hydrate(obj_bundle))
            obj.append(obj_bundle.obj)
        return obj


class SchemaDictField(DictField):
    def dehydrate(self, bundle):
        if self.attribute is not None:
            obj = getattr(bundle.obj, self.attribute)
            final_fields = _get_fields(obj)
            schema = obj.schema()

            # Run through the list and dehydrate each item
            obj_data = {}
            for key, item in obj.iteritems():
                obj_bundle = Bundle(item)
                for field_name, field_object in final_fields.iteritems():
                    obj_bundle.data[field_name] = field_object.dehydrate(obj_bundle)
                obj_data[key] = obj_bundle.data

            return self.convert(obj_data)

        if self.has_default():
            return self.convert(self.default)
        else:
            return None

    def hydrate(self, bundle):
        if self.readonly:
            return None

        # Check the bundle for data
        if self.instance_name not in bundle.data:
            if self.blank:
                return None
            elif self.attribute and getattr(bundle.obj, self.attribute, None):
                return getattr(bundle.obj, self.attribute)
            elif self.instance_name and hasattr(bundle.obj, self.instance_name):
                return getattr(bundle.obj, self.instance_name)
            elif self.has_default():
                if callable(self._default):
                    return self._default()

                return self._default
            elif self.null:
                return None
            else:
                raise ApiFieldError("The '%s' field has no data and doesn't allow a default or null value." % self.instance_name)

        obj = getattr(bundle.obj, self.attribute)
        schema = obj.schema()

        obj.clear()
        final_fields = _get_fields(obj)

        # Run through the list and hydrate each item
        obj_data = bundle.data.get(self.attribute, {})
        for key, data in obj_data.iteritems():
            obj_bundle = Bundle(obj.schema(), data)
            for field_name, field_object in final_fields.items():
                setattr(obj_bundle.obj, field_name, field_object.hydrate(obj_bundle))
            obj[key] = obj_bundle.obj
        return obj
