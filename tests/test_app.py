import json
import logging

from chalice.config import Config
from chalice.local import LocalGateway
import ga4gh.dos.test.compliance

from app import app, access_token

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestApp(ga4gh.dos.test.compliance.AbstractComplianceTest):
    @classmethod
    def setUpClass(cls):
        cls.lg = LocalGateway(app, Config())
        cls.access_token = access_token

    @classmethod
    def _make_request(cls, meth, path, headers=None, body=None, base_url='/ga4gh/dos/v1', authorized=True):
        headers = headers or {}
        if authorized:
            headers['access_token'] = cls.access_token
        r = cls.lg.handle_request(method=meth, path=base_url + path, headers=headers, body=body)
        return r['body'], r['statusCode']

    def test_auth(self):
        """
        Tests the basic access_token authentication method.
        """
        # If we don't provide a valid access token, the query should fail.
        r, status = self._make_request('GET', '/test_token', base_url='', authorized=False)
        self.assertEqual(401, status)
        self.assertFalse(json.loads(r)['authorized'])

        # If we provide a valid access token, the query should succeed.
        r, status = self._make_request('GET', '/test_token', base_url='')
        self.assertEqual(200, status)
        self.assertTrue(json.loads(r)['authorized'])

    def test_get_root(self):
        """
        Tests to see we can access the ES instance.
        """
        r, status = self._make_request('GET', '/', base_url='')
        self.assertEqual(status, 200)
        self.assertIn('version', list(json.loads(r).keys()))
