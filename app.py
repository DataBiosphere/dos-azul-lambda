import os
import json

from chalice import Chalice, Response
from boto.connection import AWSAuthConnection
import requests
import yaml

# If a key already exists on a document, it won't be
# modified by an UpdateObjectRequest, unless the key
# is in this list. See tests.
safe_keys = ['doi']


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


def check_auth():
    """
    Execute during a request to return a boolean of whether
    the request has the appropriate access_token in its headers.

    :return:
    """

    headers = app.current_request.headers
    match = False
    if 'access_token' in headers.keys():
        match = headers['access_token'] == access_token
    return match


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
DEFAULT_DOCTYPE = 'meta'
DEFAULT_ACCESS_TOKEN = 'f4ce9d3d23f4ac9dfdc3c825608dc660'

es_index = os.environ.get('ES_INDEX', DEFAULT_INDEX)
es_host = os.environ.get('ES_HOST', DEFAULT_HOST)
es_region = os.environ.get('ES_REGION', DEFAULT_REGION)
es_doctype = os.environ.get('ES_DOCTYPE', DEFAULT_DOCTYPE)
access_token = os.environ.get('ACCESS_KEY', DEFAULT_ACCESS_TOKEN)
client = ESConnection(
    region=es_region, host=es_host, is_secure=False)
app = Chalice(app_name='dos-azul-lambda')
app.debug = True

base_path = '/ga4gh/dos/v1'


@app.route('/', cors=True)
def index():
    resp = client.make_request(method='GET', path='/')
    return resp.read()


@app.route('/test_token', methods=["GET", "POST"], cors=True)
def test_token():
    """
    A convenience endpoint for testing whether an access token
    is active or not. Will return a JSON with a key `authorized`
    and a boolean regarding the key's value.

    :return:
    """
    return {'authorized': check_auth()}


def safe_get_data_object(data_object_id):
    """
    Implements a guarded attempt to get a Data Object by identifier,
    return responses to the client as necessary.

    :param data_object_id:
    :return: Tuple of data_object and source document
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

    return data_object, hit


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
    return {'data_object': safe_get_data_object(data_object_id)[0]}


@app.route("{}/dataobjects".format(base_path), methods=['GET'], cors=True)
def list_data_objects(**kwargs):
    """
    Page through the es_index and return data objects, respecting an
    alias or checksum request if it is made.

    :param kwargs:
    :return: ListDataObjectsResponse
    """
    req_body = app.current_request.query_params
    per_page = 10
    page_token = "0"
    if req_body and (req_body.get('page_size', None)):
        per_page = int(req_body.get('page_size'))
    if req_body and (req_body.get('page_token', None)):
        page_token = req_body.get('page_token')
    query = {'size': per_page + 1}
    if page_token != "0":
        query['from'] = page_token
    if req_body and req_body.get('alias', None):
        # We kludge on our own tag scheme
        alias = req_body.get('alias')
        k = alias.split(":")[0]
        v = ":".join(alias.split(":")[1:])
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
    if next_page_token:
        return {
            'data_objects': data_objects[0:per_page],
            'next_page_token': next_page_token}
    else:
        return {'data_objects': data_objects[0:per_page]}


@app.route("{}/dataobjects/{}".format(base_path, "{data_object_id}"),
           methods=['PUT'], cors=True)
def update_data_object(data_object_id):
    """
    Updates a Data Object's alias field only, while not modifying
    version information.

    :param kwargs:
    :return:
    """
    # Before anything, make sure they are allowed to make the
    # modification.
    if not check_auth():
        return Response({'msg': 'Not authorized to access '
                                'this service. Set the '
                                'access_token in request '
                                'headers.'}, status_code=403)

    # First try to get the Object specified
    data_object, source = safe_get_data_object(data_object_id)

    # Now check to see the contents don't already contain
    # any aliases we want to add.

    if app.current_request.json_body:
        update_body = app.current_request.json_body
    else:
        return Response(
                {'msg': 'Please add a data_object to '
                        'in the body of your request'}, status_code=400)

    if update_body.get('data_object', None):
        update_data_object = update_body['data_object']
    else:
        return Response(
                {'msg': 'Please add a data_object to '
                        'in the body of your request'}, status_code=400)

    new_aliases = filter(
        lambda x: x not in data_object['aliases'],
        update_data_object['aliases'])
    # if len(new_aliases) == 0:
    #     return Response(
    #         {'msg': 'No new aliases, nothing was changed. '
    #                 'Please check your request details.'}, status_code=400)

    data_object['aliases'] = data_object['aliases'] + new_aliases

    es_id = source['_id']

    # It is an implementation detail of this DOS that aliases
    # are namespaced to provide a categorical discovery
    # process.

    # We are expecting string keys as aliases, so we can add
    # them if they are not already present.

    for alias in new_aliases:
        if ':' not in alias:
            return Response(
                {'msg': 'Aliases must be namespaced by providing'
                        'a {key}:{value} structure'}, status_code=400)

    new_tuples = map(
        lambda x: [x.split(':')[0], ":".join(x.split(':')[1:])],
        new_aliases)

    # But first, to avoid overwriting existing keys, we check
    # against the contents of the source document.

    existing_keys = source['_source'].keys()

    for new_tuple in new_tuples:
        if new_tuple[0] in existing_keys and new_tuple[0] not in safe_keys:
            return Response(
                {'msg': 'Existing keys can\'t be overwritten.'
                        'Please check the alias {} is not already '
                        'in the source document.'.format(new_tuple)},
                status_code=400)

    # Now that we believe we are not overwriting an existing
    # key and that we have the source document, we can
    # attempt to perform the update.

    updated_fields = {x[0]: x[1] for x in new_tuples}

    es_update_response = client.make_request(
        method='POST', path='/{}/{}/{}/_update'.format(
            es_index, es_doctype, es_id),
        data=json.dumps({'doc': updated_fields}))

    es_update_response_body = json.loads(es_update_response.read())

    return {
        'data_object_id': data_object_id,
        'aliases': update_data_object['aliases'],
        'data_object': data_object,
        'new_aliases': new_aliases,
        'source': source,
        'es_response': es_update_response_body}


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
