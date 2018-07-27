import json
import logging
import time
from unittest import TestCase
import urllib
import uuid

from chalice.config import Config
from chalice.local import LocalGateway

from app import app, access_token

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestApp(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lg = LocalGateway(app, Config())
        cls.access_token = access_token

    def make_request(self, meth, path, headers={}, body=None, expected_status=200):
        """
        Wrapper function around :meth:`chalice.local.LocalGateway.handle_request`.
        Calls :meth:`handle_request` with reasonable defaults and checks to
        make sure that the request returns the expected status code.

        :param str meth: the HTTP method to use in the request (i.e. GET, PUT, etc.)
        :param str path: path to make a request to, sans hostname a la :meth:`handle_request`
        :param dict headers: headers to include with the request
        :param dict body: data to be included in the request body (**not** serialized as JSON)
        :param int expected_status: expected HTTP status code. If the status code
                                    is not expected, an error will be raised.
        :rtype: dict
        :returns: the response body
        """
        # Log the request being made, make the request itself, then log the response.
        logger.info("%s %s", meth, path)
        logger.debug("%s %s headers=%s body=%s", meth, path, headers, body)
        request = self.lg.handle_request(
            method=meth,
            path=path,
            headers=headers,
            body=json.dumps(body))
        rv = request['statusCode']
        logger.error("--> Request returned HTTP %d:\n%s", rv, request['body'])

        # Check to make sure the return code is what we expect
        msg = "{meth} {path} returned HTTP {rv}, expected HTTP {expected_status}"
        self.assertEqual(rv, expected_status, msg=msg.format(**locals()))

        # Return the deserialized request body
        return json.loads(request['body'])

    def get_query_url(self, path, body={}, **kwargs):
        body.update(kwargs)
        return path + '?' + urllib.urlencode(body)

    def test_auth(self):
        """
        Tests the basic access_token authentication method.
        """
        # If we don't provide a valid access token, the query should fail.
        r = self.make_request('GET', '/test_token')
        self.assertFalse(r['authorized'])

        # If we provide a valid access token, the query should succeed.
        headers = {'access_token': self.access_token}
        r = self.make_request('GET', '/test_token', headers=headers)
        self.assertTrue(r['authorized'])

    def test_get_root(self):
        """
        Tests to see we can access the ES instance.
        """
        r = self.make_request('GET', '/')
        self.assertIn('version', r.keys())

    def test_list_data_objects(self):
        """
        Test the listing feature returns a response.
        """
        pagesize = 10
        r = self.make_request('GET', '/ga4gh/dos/v1/dataobjects?page_size=' + str(pagesize))
        self.assertEqual(len(r['data_objects']), pagesize)

    def test_get_data_object(self):
        """
        Lists Data Objects and then gets one by ID.
        """
        # List all the data objects so we can pick one to test.
        r = self.make_request('GET', '/ga4gh/dos/v1/dataobjects')
        data_object_1 = r['data_objects'][0]
        r = self.make_request('GET', '/ga4gh/dos/v1/dataobjects/' + data_object_1['id'])
        data_object_2 = r['data_object']
        self.assertEqual(data_object_1, data_object_2)

    def test_get_data_bundle(self):
        """
        Lists data bundles and then gets one by ID.
        """
        # List all the data objects so we can pick one to test.
        r = self.make_request('GET', '/ga4gh/dos/v1/databundles')
        data_bundle_1 = r['data_bundles'][0]
        r = self.make_request('GET', '/ga4gh/dos/v1/databundles/' + data_bundle_1['id'])
        data_bundle_2 = r['data_bundle']
        self.assertEqual(data_bundle_1, data_bundle_2)

    def test_paging(self):
        """
        Demonstrates basic paging features.
        """
        # Make a request that will return more than one data object
        r = self.make_request('GET', '/ga4gh/dos/v1/dataobjects')
        self.assertTrue(len(r['data_objects']) > 1)

        # Now that we have a request that we know will return more than
        # one data object, we can test and see if we can use paging to
        # return only one of those objects.
        r = self.make_request('GET', '/ga4gh/dos/v1/dataobjects?page_size=1')
        self.assertEqual(len(r['data_objects']), 1)
        self.assertEqual(r['next_page_token'], '1')

        # Test that page tokens work.
        r = self.make_request('GET', '/ga4gh/dos/v1/dataobjects?page_size=1&page_token=1')
        self.assertEqual(len(r['data_objects']), 1)

    def test_update_unauthenticated(self):
        """
        Demonstrates how attempts to update a data object while not
        properly authenticated will be refused.
        """
        # List all the data objects and pick a "random" one to test.
        r = self.make_request('GET', '/ga4gh/dos/v1/dataobjects')
        data_obj = r['data_objects'][1]

        # Try and update it without specifying an auth token.auth
        r = self.make_request('PUT',
                              '/ga4gh/dos/v1/dataobjects/' + data_obj['id'],
                              headers={'content-type': 'application/json'},
                              body={'data_object': data_obj},
                              expected_status=403)

    def _test_alias(self, alias, expect_fail=False):
        """
        Helper test that demonstrates updating a data object with
        a given alias.

        :param bool expect_fail: expect that updating the alias will fail, and
                                 stop once it does. This exists only for
                                :meth:`test_update_protected_key`
        """
        # First, select a "random" object that we can test
        body = self.make_request('GET', '/ga4gh/dos/v1/dataobjects')
        data_object = body['data_objects'][9]
        url = '/ga4gh/dos/v1/dataobjects/' + data_object['id']

        # Try and update with no changes. The request is properly
        # authenticated and should return HTTP 200.
        params = {
            'headers': {
                'content-type': 'application/json',
                'access_token': self.access_token
            },
            'body': {'data_object': data_object}
        }
        self.make_request('PUT', url, **params)

        # Test adding an alias (acceptably unique to try
        # retrieving the object by the alias)
        data_object['aliases'].append(alias)

        # Try and update, this time with a change.
        params['body']['data_object'] = data_object
        # This `expect_fail` thing feels kind of dirty, but it's more concise...
        if expect_fail:
            update_response = self.make_request('PUT', url, expected_status=400, **params)
            return
        update_response = self.make_request('PUT', url, **params)
        self.assertEqual(data_object['id'], update_response['data_object_id'])

        time.sleep(2)

        # Test and see if the update took place by retrieving the object
        # and checking its aliases
        get_response = self.make_request('GET', url)
        self.assertEqual(update_response['data_object_id'], get_response['data_object']['id'])
        self.assertIn(alias, get_response['data_object']['aliases'])

        # Testing the update again by using a DOS ListDataObjectsRequest
        # to locate the object by its new alias.
        list_request = {
            'alias': alias,
            # We know the alias is unique, so even though page_size > 1
            # we expect only one result.
            'page_size': 10
        }
        list_url = self.get_query_url('/ga4gh/dos/v1/dataobjects', list_request)
        list_response = self.make_request('GET', list_url)
        self.assertEqual(1, len(list_response['data_objects']))
        self.assertIn(alias, list_response['data_objects'][0]['aliases'])

        # Tear down and remove the test alias
        params['body']['data_object']['aliases'].remove(alias)
        self.make_request('PUT', url, **params)

    def test_update_simple(self):
        """
        Demonstrates how updating a Data Object should work to
        include new fields. The lambda handles the conversion
        to the original document type.
        """
        self._test_alias('daltest:' + str(uuid.uuid1()))

    def test_update_ugly_alias(self):
        """
        Test with an 'ugly' alias to test alias key-value splitting
        """
        self._test_alias('daltest:abc:def:ghi' + str(uuid.uuid1()))

    def test_update_protected_key(self):
        """
        Try to update a data object with a 'protected key', i.e. a value
        that has already been set on an item that is not in the list of
        safe keys.
        """
        self._test_alias('file_id:GARBAGEID', expect_fail=True)
