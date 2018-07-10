import json
import logging
from unittest import TestCase
import urllib

from chalice.config import Config
from chalice.local import LocalGateway

from app import app

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestApp(TestCase):
    def setUp(self):
        self.lg = LocalGateway(app, Config())
        self.access_token = "f4ce9d3d23f4ac9dfdc3c825608dc660"

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

    def test_update(self):
        """
        Demonstrates how updating a Data Object should work to
        include new fields. The lambda handles the conversion
        to the original document type.
        """
        my_guid = 'doi:MY-IDENTIFIER'
        # First get an object to update

        data_object_id = "f4f437e8-dce2-4383-b99f-5d3da64e87a9"
        url = '/ga4gh/dos/v1/dataobjects/{}'.format(data_object_id)

        r, body = self.make_request('GET', '/ga4gh/dos/v1/dataobjects/' + data_object_id)
        data_object = body['data_object']
        # First we'll try to update something with no new
        # information. Since it's an auth'ed endpoint, this
        # should fail.

        params = {
            'headers': {
                'content-type': 'applications/json'
            },
            'body': {
                'data_object': data_object
            },
            'expected_status': 403
        }
        update_response = self.make_request('PUT', url, **params)

        # Now we will set the headers for the remainder of
        # the tests.

        params['headers']['access_token'] = self.access_token
        params['expected_status'] = 200
        update_response = self.make_request('PUT', url, **params)

        # Make sure it doesn't already include the GUID
        self.assertNotIn(my_guid, data_object['aliases'])

        # Next, we'll try to update with a "protected key", i.e.
        # a value that has already been set on an item that is
        # not in the list of safe keys.

        data_object['aliases'].append('file_id:GARBAGEID')
        params['body']['data_object'] = data_object
        params['expected_status'] = 400
        url = '/ga4gh/dos/v1/dataobjects/{}'.format(data_object['id'])
        update_response = self.make_request('PUT', url, **params)

        # Remove that "bad alias".
        data_object['aliases'] = data_object['aliases'][:-1]

        # Modify to include a GUID
        data_object['aliases'].append(my_guid)

        # Make an update request
        params['body']['data_object'] = data_object
        params['expected_status'] = 200
        update_response = self.make_request('PUT', url, **params)
        self.assertEqual(data_object['id'], update_response['data_object_id'])

        import time
        time.sleep(2)
        # Now get it again to verify it is there
        get_response = self.make_request('GET', url)
        got_data_object = get_response['data_object']
        self.assertEqual(update_response['data_object_id'], got_data_object['id'])
        self.assertIn(my_guid, got_data_object['aliases'])

        # MEAT AND POTATOES - now we actually use a DOS
        # ListDataObjectsRequest to find our item by the identifier
        # we provided.

        list_request = {
            'alias': my_guid,
            'page_size': 10}
        url = self.get_query_url('/ga4gh/dos/v1/dataobjects', list_request)
        list_response = self.make_request('GET', url)
        data_objects = list_response['data_objects']
        self.assertEqual(1, len(data_objects))
        listed_object = data_objects[0]
        self.assertIn(my_guid, listed_object['aliases'])

        # Lastly, modify the value so we can rerun tests on the
        # same object, make it an ugly thing to test the alias
        # key value splitting

        ugly_alias = "doi:abc:def:ghi"
        data_object['aliases'][-1] = ugly_alias
        params['body']['data_object'] = data_object
        update_response = self.make_request('PUT', url, **params)
        print('UPDATED RESPONSE')
        print(update_response)
        self.assertEqual(
            data_object['id'], update_response['data_object_id'])
        time.sleep(2)

        get_response = self.make_request('GET', url)
        got_data_object = get_response['data_object']
        print('GOT OBJECT')
        print(got_data_object)
        self.assertIn(ugly_alias, got_data_object['aliases'])
        time.sleep(2)
        # Now get it again to verify it is gone
        self.make_request('GET', url, headers=params['headers'])
        got_data_object = get_response['data_object']
        self.assertEqual(update_response['data_object_id'], got_data_object['id'])
        self.assertNotIn(my_guid, got_data_object['aliases'])
