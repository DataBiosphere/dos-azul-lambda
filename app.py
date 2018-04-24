import os
import json

from chalice import Chalice, Response
from boto.connection import AWSAuthConnection
import requests
import yaml


def azul_to_dos(azul):
    """
    Takes an azul document and converts it to a Data Object.

    :param azul:
    :return: Dictionary in DOS Schema
    """
    data_object = {}
    data_object['id'] = azul['file_id']
    data_object['urls'] = [{'url': url for url in azul['urls']}]
    data_object['version'] = azul['file_version']
    data_object['size'] = str(azul.get('fileSize', ""))
    data_object['checksums'] = [
        {'checksum': azul['fileMd5sum'], 'type': 'md5'}]
    # remove multiply valued items before we move into aliases
    del azul['urls']
    data_object['aliases'] = ["{}:{}".format(k, azul[k]) for k in azul.keys()]
    data_object['updated'] = azul['lastModified'] + 'Z'
    data_object['name'] = azul['title']
    return data_object


class ESConnection(AWSAuthConnection):
    def __init__(self, region, **kwargs):
        super(ESConnection, self).__init__(**kwargs)
        self._set_auth_region_name(region)
        self._set_auth_service_name('es')

    def _required_auth_capability(self):
        return [
         'hmac-v4']


# Ensure that you set 'host' below to the FQDN for YOUR
# Elasticsearch service endpoint

DEFAULT_HOST = 'search-dss-azul-commons-lx3ltgewjw5wiw2yrxftoqr7jy.us-west-2.es.amazonaws.com'  # NOQA
DEFAULT_REGION = 'us-west-2'
DEFAULT_INDEX = 'fb_index'

es_index = os.environ.get('ES_INDEX', DEFAULT_INDEX)
es_host = os.environ.get('ES_HOST', DEFAULT_HOST)
es_region = os.environ.get('ES_REGION', DEFAULT_REGION)
client = ESConnection(
    region=es_region, host=es_host, is_secure=False)
app = Chalice(app_name='dos-azul-lambda')
app.debug = True

base_path = '/ga4gh/dos/v1'


@app.route('/', cors=True)
def index():
    resp = client.make_request(method='GET', path='/')
    return resp.read()


def safe_get_data_object(data_object_id):
    """
    Implements a guarded attempt to get a Data Object by identifier,
    return responses to the client as necessary.

    :param data_object_id:
    :return:
    """
    query = {
        'query':
            {'bool': {'must': {'term': {'file_id': data_object_id}}}}}
    response = client.make_request(
        method='GET',
        path='/{}/_search'.format(es_index),
        data=json.dumps(query))
    try:
        es_response = json.loads(response.read())
    except Exception as e:
        # Return error message with 400, Bad request
        return Response({'msg': str(e)},
                        status_code=400)

    try:
        hits = es_response['hits']['hits']
    except Exception as e:
        return Response(
            {"msg": json.loads(response.read())},
            status_code=400)

    if len(hits) == 0:
        return Response(
            {"msg": "{} was not found".format(data_object_id)},
            status_code=404)
    else:
        # FIXME we just take the first
        hit = hits[0]
    try:
        data_object = azul_to_dos(hit['_source'])
    except Exception as e:
        return Response({"msg": str(e)}, status_code=400)

    # FIXME hack to guarantee identity since `file_id` is an analyzed field
    if data_object['id'] != data_object_id:
        return Response(
            {"msg": "{} was not found".format(data_object_id)},
            status_code=400)

    return data_object


@app.route("{}/dataobjects/{}".format(base_path, "{data_object_id}"),
           methods=['GET'], cors=True)
def get_data_object(data_object_id):
    """
    Gets a Data Object by file identifier by making a query
    against the azul-index and returning the first matching
    file.

    :param kwargs:
    :return:
    """

    return {'data_object': safe_get_data_object(data_object_id)}


@app.route("{}/dataobjects/list".format(base_path),
           methods=['POST'], cors=True)
def list_data_objects(**kwargs):
    """
    Page through the es_index and return data objects, respecting an
    alias or checksum request if it is made.

    :param kwargs:
    :return: ListDataObjectsResponse
    """
    req_body = app.current_request.json_body
    per_page = 10
    page_token = "0"
    if req_body and (req_body.get('page_size', None)):
        per_page = req_body.get('page_size')
    if req_body and (req_body.get('page_token', None)):
        page_token = req_body.get('page_token')
    query = {'size': per_page + 1}
    if page_token != "0":
        query['from'] = page_token
    if req_body and req_body.get('alias', None):
        # We kludge on our own tag scheme
        alias = req_body.get('alias')
        k, v = alias.split(":")
        query['query'] = {'match': {k: v}}
    resp = client.make_request(
        method='GET', path='/{}/_search'.format(es_index),
        data=json.dumps(query))
    try:
        # The elasticsearch response includes the `hits` array.
        hits = json.loads(resp.read())['hits']['hits']
    except Exception:
        # Return error message with 400, Bad request
        return Response({'msg': json.loads(resp.read())},
                        status_code=400)
    if len(hits) > per_page:
        next_page_token = str(int(page_token) + 1)
    else:
        next_page_token = None
    data_objects = map(lambda x: azul_to_dos(x['_source']), hits)
    return {
        'data_objects': data_objects[0:per_page],
        'next_page_token': next_page_token}


@app.route("{}/dataobjects/{}".format(base_path, "{data_object_id}"),
           methods=['PUT'], cors=True)
def update_data_object(data_object_id):
    """
    Updates a Data Object's alias field only, while not modifying
    version information.

    :param kwargs:
    :return:
    """
    # First try to get the Object specified
    data_object = safe_get_data_object(data_object_id)

    # Now check to see the contents don't already contain
    # any aliases we want to add.

    update_body = app.current_request.json_body

    new_aliases = filter(
        lambda x: x not in data_object['aliases'],
        update_body['aliases'])
    print(new_aliases)
    if len(new_aliases) == 0:
        return Response(
            {'msg': 'No new aliases, nothing was changed.'
                    'Please check your request details.'}, status_code=400)

    return {
        'aliases': update_body['aliases'],
        'data_object': data_object,
        'new_aliases': new_aliases}


@app.route('/swagger.json', cors=True)
def swagger():
    """
    An endpoint for returning the swagger api description.

    :return:
    """
    # FIXME replace with one hosted here
    req = requests.get("https://ga4gh.github.io/data-object-service-schemas/swagger/data_object_service.swagger.yaml")  # NOQA
    swagger_dict = yaml.load(req.content)

    swagger_dict['basePath'] = '/api/ga4gh/dos/v1'
    return swagger_dict
