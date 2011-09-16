from __future__ import absolute_import
from operator import attrgetter

from django.core.exceptions import ObjectDoesNotExist
from tastypie.bundle import Bundle
from tastypie.exceptions import BadRequest, NotFound, InvalidSortError
from tastypie.fields import (CharField, DateTimeField, BooleanField,
FloatField, DecimalField, IntegerField, TimeField, ListField, DictField)
from tastypie.resources import Resource, DeclarativeMetaclass

from ...exceptions import ResourceNotFound
from ..django.schema import Document


class DocumentDeclarativeMetaclass(DeclarativeMetaclass):
    def __new__(cls, name, bases, attrs):
        # meta = attrs.get('Meta')

        new_class = super(DocumentDeclarativeMetaclass, cls).__new__(cls, name, bases, attrs)
        fields = getattr(new_class._meta, 'fields', [])
        excludes = getattr(new_class._meta, 'excludes', [])
        field_names = new_class.base_fields.keys()

        new_class._meta.include_docs = getattr(new_class._meta, 'include_docs', True)
        new_class._meta.object_class = getattr(new_class._meta, 'object_class', Document)
        new_class._meta.view = getattr(new_class._meta, 'view', '_all_docs')

        for field_name in field_names:
            if field_name == 'resource_uri':
                continue
            if field_name in new_class.declared_fields:
                continue
            if len(fields) and not field_name in fields:
                del(new_class.base_fields[field_name])
            if len(excludes) and field_name in excludes:
                del(new_class.base_fields[field_name])

        # Add in the new fields.
        new_class.base_fields.update(new_class.get_fields(fields, excludes))

        if getattr(new_class._meta, 'include_absolute_url', True):
            if not 'absolute_url' in new_class.base_fields:
                new_class.base_fields['absolute_url'] = CharField(attribute='get_absolute_url', readonly=True)
        elif 'absolute_url' in new_class.base_fields and not 'absolute_url' in attrs:
            del(new_class.base_fields['absolute_url'])

        return new_class


class DocumentResource(Resource):
    """
    A subclass of ``Resource`` designed to work with CouchDBkits's ``Models``.

    This class will introspect a given ``Model`` and build a field list based
    on the fields found on the model.
    """
    __metaclass__ = DocumentDeclarativeMetaclass

    @classmethod
    def should_skip_field(cls, field):
        return False

    @classmethod
    def api_field_from_couch_field(cls, f, default=None):
        """
        Returns the field type that would likely be associated with each
        Django type.
        """
        result = default
        type = f.get_internal_type()

        if type in ('StringProperty', 'SchemaProperty'):
            result = CharField
        elif type in ('DateProperty', 'DateTimeProperty'):
            result = DateTimeField
        elif type == 'BooleanProperty':
            result = BooleanField
        elif type == 'FloatProperty':
            result = FloatField
        elif type == 'DecimalProperty':
            result = DecimalField
        elif type == 'IntegerProperty':
            result = IntegerField
        # elif type in ('FileField', 'ImageField'):
        #     result = FileField
        elif type == 'TimeProperty':
            result = TimeField
        elif type in ('ListProperty', 'StringListProperty'):
            result = ListField
        elif type == 'DictProperty':
            result = DictField
        elif type == 'SchemaListProperty':
            result = SchemaListField
        elif type == 'SchemaDictProperty':
            result = SchemaDictField

        return result

    @classmethod
    def get_fields(cls, fields=None, excludes=None):
        """
        Given any explicit fields to include and fields to exclude, add
        additional fields based on the associated model.
        """
        final_fields = {}
        fields = fields or []
        excludes = excludes or []

        if not cls._meta.object_class:
            return final_fields

        # TODO: Are these fields needed, since resource_uri handles the object?
        # final_fields['id'] = CharField(attribute='_id', readonly=True)
        # final_fields['rev'] = CharField(attribute='_rev', readonly=True)
        for f in cls._meta.object_class._properties.values():
            # If the field name is already present, skip
            if f.name in cls.base_fields:
                continue

            # If field is not present in explicit field listing, skip
            if fields and f.name not in fields:
                continue

            # If field is in exclude list, skip
            if excludes and f.name in excludes:
                continue

            if cls.should_skip_field(f):
                continue

            kwargs = {
                'attribute': f.name,
                'blank': not f.required,
                'default': f.default,
            }

            api_field_class = cls.api_field_from_couch_field(f)

            final_fields[f.name] = api_field_class(**kwargs)
            final_fields[f.name].instance_name = f.name

        return final_fields

    def get_object_list(self, request):
        return self._meta.object_class.view(self._meta.view, include_docs=self._meta.include_docs)

    def obj_get_list(self, request=None, **kwargs):
        try:
            queryset = self.get_object_list(request)
            return self.apply_authorization_limits(request, queryset.all())
        except ResourceNotFound:
            raise BadRequest('Invalid resource lookup data provided (mismatched type).')

    def obj_get(self, request=None, **kwargs):
        # Use the view as a filter, so that we can't get object that don't belong to the view
        object_list = self._meta.object_class.view(self._meta.view, key=kwargs['pk'], limit=1, include_docs=self._meta.include_docs)
        if not object_list:
            raise NotFound('Invalid resource lookup data provided (mismatched type).')
        object_list = object_list.first()
        return self.apply_authorization_limits(request, object_list)

    def obj_create(self, bundle, request=None, **kwargs):
        bundle.obj = self._meta.object_class()

        for key, value in kwargs.items():
            setattr(bundle.obj, key, value)

        bundle = self.full_hydrate(bundle)

        # Save the main object.
        bundle.obj.save()

        return bundle

    # def obj_delete_list(self, request=None, **kwargs):
    #     try:
    #         queryset = self.get_object_list(request)
    #         authed_object_list = self.apply_authorization_limits(request, queryset.all())
    #     except ResourceNotFound:
    #         raise BadRequest('Invalid resource lookup data provided (mismatched type).')
    # 
    #     if hasattr(authed_object_list, 'delete'):
    #         # It's likely a ``QuerySet``. Call ``.delete()`` for efficiency.
    #         authed_object_list.delete()
    #     else:
    #         for authed_obj in authed_object_list:
    #             authed_obj.delete()

    def obj_delete(self, request=None, **kwargs):
        try:
            obj = self.obj_get(request, **kwargs)
        except ObjectDoesNotExist:
            raise NotFound("A model instance matching the provided arguments could not be found.")

        obj.delete()

    # def rollback(self, bundles):
    #     for bundle in bundles:
    #         if bundle.obj and getattr(bundle.obj, 'pk', None):
    #             bundle.obj.delete()

    def get_resource_uri(self, bundle_or_obj):
        """
        Handles generating a resource URI for a single resource.

        Uses the model's ``pk`` in order to create the URI.
        """
        kwargs = {
            'resource_name': self._meta.resource_name,
        }

        if isinstance(bundle_or_obj, Bundle):
            kwargs['pk'] = bundle_or_obj.obj.get_id
        else:
            kwargs['pk'] = bundle_or_obj.get_id

        if self._meta.api_name is not None:
            kwargs['api_name'] = self._meta.api_name

        return self._build_reverse_url("api_dispatch_detail", kwargs=kwargs)

    # def build_filters(self, filters=None):
    #     """
    #     Allows for the filtering of applicable objects.
    # 
    #     This needs to be implemented at the user level.'
    # 
    #     ``ModelResource`` includes a full working version specific to Django's
    #     ``Models``.
    #     """
    #     return filters

    def apply_sorting(self, obj_list, options=None):
        if options is None:
            options = {}

        parameter_name = 'order_by'

        if not parameter_name in options:
            return obj_list

        if hasattr(options, 'getlist'):
            order_bits = options.getlist(parameter_name)
        else:
            order_bits = options.get(parameter_name)

            if not isinstance(order_bits, (list, tuple)):
                order_bits = [order_bits]

        # Reverse so we can sort by the least significant key first
        order_bits.reverse()

        for order_by in order_bits:
            field_name = order_by
            reverse = False

            if field_name.startswith('-'):
                field_name = field_name[1:]
                reverse = True

            if not field_name in self.fields:
                # It's not a field we know about. Move along citizen.
                raise InvalidSortError("No matching '%s' field for ordering on." % field_name)

            # If the ordering list is empty assume everything is good
            if self._meta.ordering and not field_name in self._meta.ordering:
                raise InvalidSortError("The '%s' field does not allow ordering." % field_name)

            if self.fields[field_name].attribute is None:
                raise InvalidSortError("The '%s' field has no 'attribute' for ordering with." % field_name)

            obj_list = sorted(obj_list, key=attrgetter(field_name), reverse=reverse)

        return obj_list


# Circular import
from .fields import SchemaListField, SchemaDictField
