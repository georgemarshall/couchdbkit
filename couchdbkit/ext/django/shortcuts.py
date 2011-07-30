from django.http import Http404

from ...exceptions import ResourceNotFound

def get_object_or_404(klass, *args, **kwargs):
    """
    Uses get() to return an object, or raises a Http404 exception if the object
    does not exist.

    klass may be a Model, Manager, or QuerySet object. All other passed
    arguments and keyword arguments are used in the get() query.

    Note: Like with get(), an MultipleObjectsReturned will be raised if more than one
    object is found.
    """
    queryset = klass
    try:
        return queryset.get(*args, **kwargs)
    except ResourceNotFound:
        raise Http404('No %s matches the given query.' % queryset._meta.object_name)
