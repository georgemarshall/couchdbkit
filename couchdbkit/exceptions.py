# -*- coding: utf-8 -
#
# This file is part of couchdbkit released under the MIT license. 
# See the NOTICE for more information.

"""
All exceptions used in couchdbkit.
"""
from restkit.errors import ResourceError

class InvalidAttachment(Exception):
    "Raised when an attachment is invalid"
    pass

class DuplicatePropertyError(Exception):
    "Exception raised when there is a duplicate property in a model"
    pass

class BadValueError(Exception):
    "Exception raised when a value can't be validated or is required"
    pass

class MultipleResultsFound(Exception):
    "Exception raised when more than one object is returned"
    pass

class NoResultFound(Exception):
    "Exception returned when no results are found"
    pass

class ReservedWordError(Exception):
    "Exception raised when a reserved word is used in Document schema"
    pass

class DocsPathNotFound(Exception):
    "Exception raised when path given for docs isn't found"
    pass

class BulkSaveError(Exception):
    """
    Exception raised when bulk save contains errors. Errors are saved in
    `errors` property.
    """
    def __init__(self, errors, results, *args):
        self.errors = errors
        self.results = results

class ViewServerError(Exception):
    "Exception raised by view server"
    pass

class MacroError(Exception):
    "Exception raised when macro parsiing error in functions"
    pass

class DesignerError(Exception):
    "Unkown exception raised by the designer"
    pass

class ResourceNotFound(ResourceError):
    "Exception raised when resource is not found"
    pass

class ResourceConflict(ResourceError):
    "Exception raised when there is conflict while updating"
    pass

class PreconditionFailed(ResourceError):
    """
    Exception raised when 412 HTTP error is received in response to a request
    """
    pass
