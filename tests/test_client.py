# -*- coding: utf-8 -*-
#
# This file is part of couchdbkit released under the MIT license.
# See the NOTICE for more information.
__author__ = u'benoitc@e-engura.com (Benoît Chesneau)'

from urlparse import urlparse, ParseResult
try:
    import unittest2 as unittest
except ImportError:
    import unittest

from couchdbkit import (
    BulkSaveError, CouchdbResource, Database, Document, ResourceNotFound,
    ResourceConflict, Server, resource
)


class ClientServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_names = ('couchdbkit_test', 'couchdbkit/test')
        cls.server = Server()
        cls.server_url = 'http://127.0.0.1:5984/'

    @classmethod
    def tearDownClass(cls):
        # Make sure our databases are extra deleted
        for db_name in cls.server.all_dbs():
            for db_prefix in cls.db_names:
                if db_name.startswith(db_prefix):
                    cls.server.delete_db(db_name)

    def test_server_initialization(self):
        """
        Server initialization
        """
        self.assertRaises(ValueError, Server, None)

        Server(self.server_url, resource_class=resource.CouchdbResource)

    def test_server_active_tasks(self):
        """
        Server active tasks
        """
        active_tasks = self.server.active_tasks()
        self.assertIsNotNone(active_tasks)

    def test_server_info(self):
        """
        Server info
        """
        info = self.server.info()
        self.assertIn('version', info)

    def test_server_uuids(self):
        """
        Get UUIDs from server
        """
        result = self.server.uuids()
        self.assertIn('uuids', result)
        self.assertEquals(len(result['uuids']), 1)

        result = self.server.uuids(count=5)
        self.assertIn('uuids', result)
        self.assertEquals(len(result['uuids']), 5)

    def test_stored_uuids(self):
        """
        Get UUIDS from class store
        """
        result = self.server.next_uuid()
        self.assertIsInstance(result, basestring)
        self.assertEqual(len(self.server._uuids), 999)

        result2 = self.server.next_uuid()
        self.assertNotEqual(result, result2)
        self.assertEqual(len(self.server._uuids), 998)

    def test_create_db(self):
        """
        Database creation
        """
        for db_name in self.db_names:
            # Check to make sure we have a clean slate
            self.server.delete_db(db_name)

            # Creation success and exsistance
            self.assertTrue(self.server.create_db(db_name))
            self.assertIn(db_name, self.server.all_dbs())

            # Duplicate creation and failure
            self.assertFalse(self.server.create_db(db_name))

            # Remove database
            self.assertTrue(self.server.delete_db(db_name))
            self.assertFalse(self.server.delete_db(db_name))

    def test_get_db(self):
        """
        Database retrieval
        """
        for db_name in self.db_names:
            # Get non-exsistant database
            self.assertIsNone(self.server.get_db(db_name))

            #Create database
            self.assertTrue(self.server.create_db(db_name))

            # Get database
            self.assertIsInstance(self.server.get_db(db_name), self.server.database_class)

            # Remove database
            self.server.delete_db(db_name)

    def test_get_or_create_db(self):
        """
        Get or create database
        """
        for db_name in self.db_names:
            # Check to make sure we have a clean slate
            self.server.delete_db(db_name)

            # Create database
            create_db = self.server.get_or_create_db(db_name)
            self.assertIsInstance(create_db, self.server.database_class)
            self.assertIn(db_name, self.server.all_dbs())

            # Get the database
            get_db = self.server.get_or_create_db(db_name)
            self.assertIsInstance(get_db, self.server.database_class)
            self.assertEqual(create_db.name, get_db.name)

            # Remove database
            self.server.delete_db(db_name)

    def test_replicate_db(self):
        """
        Replicate a database
        """
        r_name = '_copy'
        for db_name in self.db_names:
            #Create source database
            source = self.server.get_or_create_db(db_name)

            # Replicate to non-exsistant target database
            self.assertFalse(self.server.replicate(source, db_name + r_name))

            # Create target database
            target = self.server.get_or_create_db(db_name + r_name)

            # Replicate database
            self.assertTrue(self.server.replicate(source, target))

            # Remove database
            self.server.delete_db(db_name)
            self.server.delete_db(db_name + r_name)

    def test_create_invalid_db(self):
        """
        Database with invalid name
        """
        self.assertRaises(ValueError, self.server.create_db, '123ab')


if __name__ == '__main__':
    unittest.main()
