from __future__ import absolute_import
from operator import attrgetter

from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models.sql.constants import QUERY_TERMS, LOOKUP_SEP
from django.http import QueryDict
from tastypie import http
from tastypie.bundle import Bundle
from tastypie.constants import ALL, ALL_WITH_RELATIONS
from tastypie.exceptions import BadRequest, NotFound, InvalidFilterError, InvalidSortError
from tastypie.fields import (CharField, DateTimeField, BooleanField,
FloatField, DecimalField, IntegerField, TimeField, ListField, DictField)
from tastypie.resources import Resource, DeclarativeMetaclass
from tastypie.utils import dict_strip_unicode_keys

from ...exceptions import ResourceNotFound
from ..django.schema import Document


class DocumentDeclarativeMetaclass(DeclarativeMetaclass):
    def __new__(cls, name, bases, attrs):
        new_class = super(DocumentDeclarativeMetaclass, cls).__new__(cls, name, bases, attrs)
        include_fields = getattr(new_class._meta, 'fields', [])
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
            if len(include_fields) and not field_name in include_fields:
                del(new_class.base_fields[field_name])
            if len(excludes) and field_name in excludes:
                del(new_class.base_fields[field_name])

        # Add in the new fields.
        new_class.base_fields.update(new_class.get_fields(include_fields, excludes))

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
        # TODO: Add support for attachments
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

        final_fields['_id'] = CharField(attribute='_id', readonly=True)
        # final_fields['_rev'] = CharField(attribute='_rev', readonly=True)
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
        filters = QueryDict('', mutable=True)

        if hasattr(request, 'GET'):
            # Grab a mutable copy.
            filters = request.GET.copy()

        # Update with the provided kwargs.
        filters.update(kwargs)
        applicable_filters = self.build_filters(filters=filters)

        base_object_list = self.apply_filters(request, applicable_filters)
        return self.apply_authorization_limits(request, base_object_list)

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

    def obj_update(self, bundle, request=None, **kwargs):
        """
        A ORM-specific implementation of ``obj_update``.
        """
        if not bundle.obj or not bundle.obj.pk:
            bundle.obj = self.obj_get(request, **kwargs)

        bundle = self.full_hydrate(bundle)

        # Save the main object.
        bundle.obj.save()

        return bundle

    def obj_delete_list(self, request=None, **kwargs):
        filters = QueryDict('', mutable=True)

        if hasattr(request, 'GET'):
            # Grab a mutable copy.
            filters = request.GET.copy()

        # Update with the provided kwargs.
        filters.update(kwargs)
        applicable_filters = self.build_filters(filters=filters)

        try:
            base_object_list = self.apply_filters(request, applicable_filters)
            authed_object_list = self.apply_authorization_limits(request, base_object_list)
        except ResourceNotFound:
            raise BadRequest('Invalid resource lookup data provided (mismatched type).')

        if hasattr(authed_object_list, 'delete'):
            # It's likely a ``QuerySet``. Call ``.delete()`` for efficiency.
            authed_object_list.delete()
        else:
            for authed_obj in authed_object_list:
                authed_obj.delete()

    def obj_delete(self, request=None, **kwargs):
        try:
            obj = self.obj_get(request, **kwargs)
        except ObjectDoesNotExist:
            raise NotFound("A model instance matching the provided arguments could not be found.")
        obj.delete()

    def rollback(self, bundles):
        for bundle in bundles:
            if bundle.obj and getattr(bundle.obj, 'pk', None):
                bundle.obj.delete()

    def get_resource_uri(self, bundle_or_obj):
        """
        Handles generating a resource URI for a single resource.

        Uses the model's ``pk`` in order to create the URI.
        """
        kwargs = {
            'resource_name': self._meta.resource_name,
        }

        if isinstance(bundle_or_obj, Bundle):
            kwargs['pk'] = bundle_or_obj.obj.pk
        else:
            kwargs['pk'] = bundle_or_obj.id

        if self._meta.api_name is not None:
            kwargs['api_name'] = self._meta.api_name

        return self._build_reverse_url("api_dispatch_detail", kwargs=kwargs)

    def check_filtering(self, field_name, filter_type='exact', filter_bits=None):
        if filter_bits is None:
            filter_bits = []

        if not field_name in self._meta.filtering:
            raise InvalidFilterError("The '%s' field does not allow filtering." % field_name)

        # Check to see if it's an allowed lookup type.
        if not self._meta.filtering[field_name] in (ALL, ALL_WITH_RELATIONS):
            # Must be an explicit whitelist.
            if not filter_type in self._meta.filtering[field_name]:
                raise InvalidFilterError("'%s' is not an allowed filter on the '%s' field." % (filter_type, field_name))

        if self.fields[field_name].attribute is None:
            raise InvalidFilterError("The '%s' field has no 'attribute' for searching with." % field_name)

        # Check to see if it's a relational lookup and if that's allowed.
        if len(filter_bits):
            if not getattr(self.fields[field_name], 'is_related', False):
                raise InvalidFilterError("The '%s' field does not support relations." % field_name)

            if not self._meta.filtering[field_name] == ALL_WITH_RELATIONS:
                raise InvalidFilterError("Lookups are not allowed more than one level deep on the '%s' field." % field_name)

            # Recursively descend through the remaining lookups in the filter,
            # if any. We should ensure that all along the way, we're allowed
            # to filter on that field by the related resource.
            related_resource = self.fields[field_name].get_related_resource(None)
            return [self.fields[field_name].attribute] + related_resource.check_filtering(filter_bits[0], filter_type, filter_bits[1:])

        return [self.fields[field_name].attribute]

    def apply_filters(self, request, applicable_filters):
        try:
            queryset = self.get_object_list(request)
            result = queryset.all()

            for attr, filt in applicable_filters.iteritems():
                filters = {
                    'exact': lambda x: getattr(x, attr) == filt['value'],
                    'iexact': lambda x: getattr(x, attr).lower() == filt['value'].lower(),
                    'contains': lambda x: filt['value'] in getattr(x, attr),
                    'icontains': lambda x: filt['value'].lower() in getattr(x, attr).lower(),
                    # 'in': lambda x: filt['value'] in getattr(x, attr),  # TODO: implament this
                    'gt': lambda x: getattr(x, attr) > filt['value'],
                    'gte': lambda x: getattr(x, attr) >= filt['value'],
                    'lt': lambda x: getattr(x, attr) < filt['value'],
                    'lte': lambda x: getattr(x, attr) <= filt['value'],
                    'startswith': lambda x: getattr(x, attr).startswith(filt['value']),
                    'istartswith': lambda x: getattr(x, attr).lower().startswith(filt['value'].lower()),
                    'endswith': lambda x: getattr(x, attr).endswith(filt['value']),
                    'iendswith': lambda x: getattr(x, attr).lower().endswith(filt['value'].lower()),
                    # 'range': lambda x: None,
                    'year': lambda x: getattr(x, attr).year == filt['value'],
                    'month': lambda x: getattr(x, attr).month == filt['value'],
                    'day': lambda x: getattr(x, attr).day == filt['value'],
                    'week_day': lambda x: getattr(x, attr).weekday() == filt['value'],
                    'isnull': lambda x: getattr(x, attr) is None if filt['value'] else getattr(x, attr) is not None,
                    # 'search': lambda x: None,
                    # 'regex': lambda x: None,
                    # 'iregex': lambda x: None,
                }
                result = filter(filters[filt['filter_type']], result)
            return result
        except ResourceNotFound:
            raise BadRequest('Invalid resource lookup data provided (mismatched type).')

    def build_filters(self, filters=None):
        if filters is None:
            filters = {}

        qs_filters = {}

        for filter_expr, value in filters.items():
            filter_bits = filter_expr.split(LOOKUP_SEP)
            field_name = filter_bits.pop(0)
            filter_type = 'exact'

            if not field_name in self.fields:
                # It's not a field we know about. Move along citizen.
                continue

            if len(filter_bits) and filter_bits[-1] in QUERY_TERMS.keys():
                filter_type = filter_bits.pop()

            lookup_bits = self.check_filtering(field_name, filter_type, filter_bits)

            # Is the field defined in our resource?
            field = getattr(self, field_name)

            # If we have a field defined use its type conversion
            if field:
                value = field.convert(value)
            elif isinstance(value, basestring):
                if value.lower() in ('true', 'yes'):
                    value = True
                elif value.lower() in ('false', 'no'):
                    value = False
                elif value.lower() in ('nil', 'none', 'null'):
                    value = None
                # elif value.isnumeric():
                #     value = int(value)

            # Split on ',' if not empty string and either an in or range filter.
            if filter_type in ('in', 'range') and len(value):
                if hasattr(filters, 'getlist'):
                    value = filters.getlist(filter_expr)
                else:
                    value = value.split(',')

            qs_filters[field_name] = {
                'filter_type': filter_type,
                'value': value
            }

        return dict_strip_unicode_keys(qs_filters)

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

    def put_detail(self, request, **kwargs):
        deserialized = self.deserialize(request, request.raw_post_data, format=request.META.get('CONTENT_TYPE', 'application/json'))
        deserialized = self.alter_deserialized_detail_data(request, deserialized)
        bundle = self.build_bundle(data=dict_strip_unicode_keys(deserialized), request=request)
        self.is_valid(bundle, request)

        updated_bundle = self.obj_update(bundle, request=request, **self.remove_api_resource_names(kwargs))

        if not self._meta.always_return_data:
            return http.HttpNoContent()
        else:
            updated_bundle = self.full_dehydrate(updated_bundle)
            updated_bundle = self.alter_detail_data_to_serialize(request, updated_bundle)
            return self.create_response(request, updated_bundle, response_class=http.HttpAccepted)


class NamespacedDocumentResource(DocumentResource):
    """A DocumentResource subclass that respects Django namespaces."""
    def _build_reverse_url(self, name, args=None, kwargs=None):
        namespaced = "%s:%s" % (self._meta.urlconf_namespace, name)
        return reverse(namespaced, args=args, kwargs=kwargs)


# Circular import
from .fields import SchemaListField, SchemaDictField
