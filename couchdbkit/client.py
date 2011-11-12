# -*- coding: utf-8 -*-
#
# This file is part of couchdbkit released under the MIT license.
# See the NOTICE for more information.
"""
Client implementation for CouchDB access. It allows you to manage a CouchDB
server, databases, documents and views. All objects mostly reflect python
objects for convenience. Server and Database objects for example, can be
used as easy as a dict.

Example:

    >>> from couchdbkit import Server
    >>> server = Server()
    >>> db = server.create_db('couchdbkit_test')
    >>> doc = { 'string': 'test', 'number': 4 }
    >>> db.save_doc(doc)
    >>> docid = doc['_id']
    >>> doc2 = db.get(docid)
    >>> doc['string']
    u'test'
    >>> del db[docid]
    >>> docid in db
    False
    >>> del server['simplecouchdb_test']

"""
from __future__ import absolute_import

from collections import deque
from itertools import groupby
from mimetypes import guess_type
from urlparse import urlparse, ParseResult
import time
import urllib

from restkit import BasicAuth
from restkit.util import url_quote
from restkit.errors import RequestFailed

from . import resource
from .bucket import Database
from .exceptions import (
    InvalidAttachment, NoResultFound, ResourceNotFound, ResourceConflict,
    BulkSaveError, MultipleResultsFound, PreconditionFailed
)
from .utils import validate_dbname

DEFAULT_UUID_BATCH_COUNT = 1000
UNKOWN_INFO = {}

__all__ = ['Server']


class Server(object):
    """
    Server object that allows you to access and manage a couchdb node. A
    Server object can be used like any `dict` object.
    """
    database_class = Database
    resource_class = resource.CouchdbResource
    uuid_batch_count = DEFAULT_UUID_BATCH_COUNT

    def __init__(self, url='http://127.0.0.1:5984/',
            resource_class=None, resource_instance=None,
            **client_opts):
        """
        Constructor for Server object

        @param uri: uri of CouchDb host
        @param uuid_batch_count: max of uuids to get in one time
        @param resource_instance: `restkit.resource.CouchdbDBResource` instance.
            It alows you to set a resource class with custom parameters.
        """
        if not isinstance(url, basestring):
            raise ValueError('Server uri is missing')
        self.url = urlparse(url)
        filters = []

        # if isinstance(uri, dict):
        #     uri_settings = uri  # Change the refrence to the dict

        #     uri = uri_settings['URL']
        #     # Blank credentials are valid for the admin party
        #     user = uri_settings.get('USER', '')
        #     password = uri_settings.get('PASSWORD', '')

        #     filters.append(BasicAuth(user, password))

        # if not uri or uri is None:
        #     raise ValueError("Server uri is missing")

        # if uri.endswith("/"):
        #     uri = uri[:-1]

        # self.uri = uri
        url_dict = self.url._asdict()
        url_dict.update(fragment='', params='', query='', path='')

        if resource_class is not None:
            self.resource_class = resource_class

        if resource_instance and isinstance(resource_instance, resource.CouchdbResource):
            resource_instance.initial['uri'] = ParseResult(**url_dict).geturl()
            self.resource = resource_instance.clone()
            if client_opts:
                self.res.client_opts.update(client_opts)
        else:
            self.resource = self.resource_class(ParseResult(**url_dict).geturl(), filters=filters, **client_opts)
        # self.res = self.resource
        self._uuids = deque()

    # def __contains__(self, dbname):
    #     try:
    #         self.res.head('/%s/' % url_quote(dbname, safe=":"))
    #     except:
    #         return False
    #     return True

    # def __iter__(self):
    #     for dbname in self.all_dbs():
    #         yield Database(self._db_uri(dbname), server=self)

    # def __len__(self):
    #     return len(self.all_dbs())

    # def __nonzero__(self):
    #     return (len(self) > 0)

    def info(self):
        """ info of server

        @return: dict
        """
        try:
            return self.resource.get().json_body
        except Exception:
            return UNKOWN_INFO

    def all_dbs(self):
        """
        Get a list of databases in CouchDb host
        """
        return self.resource.get('_all_dbs').json_body

    def get_db(self, name, **params):
        """
        Try to return a Database object for dbname.

        """
        try:
            return self.database_class(self, name, **params)
        except ResourceNotFound:
            return None

    def create_db(self, name, **params):
        """ Create a database on CouchDb host

        @param dname: str, name of db
        @param param: custom parameters to pass to create a db. For
        example if you use couchdbkit to access to cloudant or bigcouch:

            Ex: q=12 or n=4

        See https://github.com/cloudant/bigcouch for more info.

        @return: Database instance if it's ok or dict message
        """
        validate_dbname(name)
        try:
            self.resource.put(urllib.quote_plus(name), **params)
        except PreconditionFailed:
            return False
        else:
            return True

    def get_or_create_db(self, name, **params):
        """
        Try to return a Database object for dbname. If
        database doest't exist, it will be created.

        """
        self.create_db(name, **params)
        return self.database_class(self, name, **params)

    def delete_db(self, name, **params):
        """
        Delete database
        """
        try:
            self.resource.delete(urllib.quote_plus(name), **params)
        except ResourceNotFound:
            return False
        else:
            return True

    #TODO: maintain list of replications
    def replicate(self, source, target, **params):
        """
        simple handler for replication

        @param source: str, URI or dbname of the source
        @param target: str, URI or dbname of the target
        @param params: replication options

        More info about replication here :
        http://wiki.apache.org/couchdb/Replication

        """
        payload = {
            'source': source.resource.uri if isinstance(source, Database) else source,
            'target': target.resource.uri if isinstance(target, Database) else target,
        }
        payload.update(params)
        try:
            self.resource.post('_replicate', payload=payload, **params).json_body
        except ResourceNotFound:
            return False
        else:
            return True

    def active_tasks(self):
        """
        Return active tasks
        """
        resp = self.resource.get('_active_tasks')
        return resp.json_body

    def uuids(self, count=1):
        return self.resource.get('_uuids', count=count).json_body

    def next_uuid(self):
        """
        return an available uuid from couchdbkit
        """
        try:
            return self._uuids.pop()
        except IndexError:
            self._uuids.extend(self.uuids(count=self.uuid_batch_count)['uuids'])
            return self._uuids.pop()
