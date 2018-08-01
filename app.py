import os
import json

from chalice import Chalice, Response
from boto.connection import AWSAuthConnection
import requests
import yaml


def azul_to_obj(result):
    """
    Takes an Azul ElasticSearch result and converts it to a DOS data
    object.

    :param result: the ElasticSearch result dictionary
    :return: DataObject
    """
    azul = result['_source']
    data_object = {}
    data_object['id'] = azul['file_id']
    data_object['urls'] = [{'url': url} for url in azul['urls']]
    data_object['version'] = azul['file_version']
    data_object['size'] = str(azul.get('fileSize', ''))
    data_object['checksums'] = [
        {'checksum': azul['fileMd5sum'], 'type': 'md5'}]
    data_object['aliases'] = azul['aliases']
    data_object['updated'] = azul['lastModified'] + 'Z'
    data_object['name'] = azul['title']
    return data_object


def azul_to_bdl(result):
    """
    Takes an Azul ElasticSearch result and converts it to a DOS data
    bundle.

    :param result: the ElasticSearch result dictionary
    :return: DataBundle
    """
    azul = result['_source']
    bundle = {
        'id': azul['id'],
        'version': azul['version'],
        'checksums': [{'checksum': c.split(':')[0], 'type': c.split(':')[1]} for c in azul['checksums']],
        'updated': azul['updated'] + 'Z',
        'created': azul['created'] + 'Z',
        'descrption': azul.get('description', ''),
        'data_object_ids': azul['data_object_ids'],
    }
    # remove multiply valued items before we move into aliases
    del azul['checksums']
    bundle['aliases'] = ['{}:{}'.format(k, v) for k, v in azul.items()]
    return bundle


def check_auth():
    """
    Execute during a request to check the ``access_token`` key in the
    request headers.
    :return: True if ``access_token`` is valid, False otherwise
    :rtype: bool
    """
    return app.current_request.headers.get('access_token', None) == access_token


class ESConnection(AWSAuthConnection):
    def __init__(self, region, **kwargs):
        super(ESConnection, self).__init__(**kwargs)
        self._set_auth_region_name(region)
        self._set_auth_service_name('es')

    def _required_auth_capability(self):
        return ['hmac-v4']


# Ensure that you set 'host' below to the FQDN for YOUR
# Elasticsearch service endpoint

DEFAULT_HOST = 'search-dss-azul-commons-lx3ltgewjw5wiw2yrxftoqr7jy.us-west-2.es.amazonaws.com'
DEFAULT_REGION = 'us-west-2'
DEFAULT_ACCESS_TOKEN = 'f4ce9d3d23f4ac9dfdc3c825608dc660'

INDEXES = {
    'data_obj': os.environ.get('DATA_OBJ_INDEX', 'fb_index'),
    'data_bdl': os.environ.get('DATA_BDL_INDEX', 'db_index'),
}

DOCTYPES = {
    'data_obj': os.environ.get('DATA_OBJ_DOCTYPE', 'meta'),
    'data_bdl': os.environ.get('DATA_BDL_DOCTYPE', 'databundle'),
}

es_host = os.environ.get('ES_HOST', DEFAULT_HOST)
es_region = os.environ.get('ES_REGION', DEFAULT_REGION)
access_token = os.environ.get('ACCESS_KEY', DEFAULT_ACCESS_TOKEN)
client = ESConnection(
    region=es_region, host=es_host, is_secure=False)
app = Chalice(app_name='dos-azul-lambda')
app.debug = os.environ.get('DEBUG', False) == 'True'

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
    """
    body = {'authorized': check_auth()}
    return Response(body, status_code=200 if body['authorized'] else 401)


def es_query(query, index, size):
    """
    Queries the configured ElasticSearch instance and returns the
    results as a list of dictionaries

    :param dict query: the ElasticSearch DSL query, as it would appear under
                       the 'query' key of the request body
    :param str index: the name of the index to query
    :param int size: the amount of results to return
    :raises RuntimeError: if the response from the ElasticSearch instance
                          loads successfully but can't be understood by
                          dos-azul-lambda
    :rtype: list
    """
    dsl = {'size': size, 'query': query}
    query = client.make_request(method='GET', data=json.dumps(dsl),
                                path='/{index}/_search'.format(index=index))
    response = json.loads(query.read())
    try:
        hits = response['hits']['hits']
    except KeyError:
        raise RuntimeError("ElasticSearch returned an unexpected response")

    return hits


def azul_match_field(index, key, val, size=1):
    """
    Wrapper function around :func:`es_query`. Should be used for queries
    where you expect only one result (e.g. GetDataBundle).
    :param str index: the name of the index to query
    :param str key: the key of the field to match against
    :param str val: the value of the field to match against
    :param int size: the amount of results to return
    :raises LookupError: if no results are returned
    :rtype: :class:`AzulDocument`
    """
    results = es_query(index=index, size=size,
                       query={'bool': {'must': {'term': {key: val}}}})
    if len(results) < 1:
        raise LookupError("Query returned no results")
    return results[0]


def azul_match_alias(index, alias, from_=None, size=10):
    """
    Wrapper function around :func:`es_query`. By default, this function
    will return more than one result (intended for usage in ListDataObjects,
    etc.
    :param str index: the name of the index to query
    :param str key: the key of the alias to match against
    :param str val: the value of the alias to match against
    :param str from_: page_token
    :param int size: the amount of results to return
    :raises LookupError: if no results are returned
    :rtype: list
    """
    dsl = {'term': {'aliases.keyword': alias}}
    if from_:
        dsl['from'] = from_
    return es_query(index=index, query=dsl, size=size)


@app.route(base_path + '/dataobjects/{data_object_id}', methods=['GET'], cors=True)
def get_data_object(data_object_id):
    """
    Gets a data object by file identifier by making a query against the
    configured data object index and returns the first matching file.

    :param data_object_id: the id of the data object
    :raises LookupError: if no data object is found for the given query
    :rtype: DataObject
    """
    try:
        data_obj = azul_to_obj(azul_match_field(index=INDEXES['data_obj'],
                                                key='file_id', val=data_object_id))
        # Double check to verify identity (since `file_id` is an analyzed field)
        if data_obj['id'] != data_object_id:
            raise LookupError
    # azul_match_field will also raise a LookupError if no results are returned
    except LookupError:
        return Response({'msg': "Data object not found."}, status_code=404)
    return Response({'data_object': data_obj}, status_code=200)


@app.route(base_path + '/databundles/{data_bundle_id}', methods=['GET'], cors=True)
def get_data_bundle(data_bundle_id):
    """
    Gets a data bundle by its identifier by making a query against the
    configured data bundle index. Returns the first matching file.

    :param data_bundle_id: the id of the data bundle
    :raises LookupError: if no data bundle is found for the given query
    :rtype: DataBundle
    """
    try:
        data_bdl = azul_to_bdl(azul_match_field(index=INDEXES['data_bdl'],
                                                key='id', val=data_bundle_id))
        # Double check to verify identity (since `file_id` is an analyzed field)
        if data_bdl['id'] != data_bundle_id:
            raise LookupError
    # azul_match_field will also raise a LookupError if no results are returned
    except LookupError:
        return Response({'msg': "Data bundle not found."}, status_code=404)
    return Response({'data_bundle': data_bdl}, status_code=200)


@app.route(base_path + '/dataobjects', methods=['GET'], cors=True)
def list_data_objects(**kwargs):
    """
    Page through the data objects index and return data objects,
    respecting an alias or checksum request if it is made.

    :rtype: ListDataObjectsResponse
    """
    req_body = app.current_request.query_params or {}
    page_token = req_body.get('page_token', 0)
    per_page = int(req_body.get('page_size', 10))
    if req_body.get('alias', None):
        results = azul_match_alias(index=INDEXES['data_obj'],
                                   alias=req_body['alias'], size=per_page + 1,
                                   from_=page_token if page_token != 0 else None)
    else:
        results = es_query(query={}, index=INDEXES['data_obj'], size=per_page + 1)

    if len(results) > per_page:
        next_page_token = str(int(page_token) + 1)
    else:
        next_page_token = None
    data_objects = map(azul_to_obj, results)
    response = {'data_objects': data_objects[0:per_page]}
    if next_page_token:
        response['next_page_token'] = next_page_token
    return response


@app.route(base_path + '/databundles', methods=['GET'], cors=True)
def list_data_bundles(**kwargs):
    """
    Page through the data bundles index and return data bundles,
    respecting an alias or checksum request if it is made.

    :rtype: ListDataBundlesResponse
    """
    req_body = app.current_request.query_params or {}
    page_token = req_body.get('page_token', 0)
    per_page = int(req_body.get('page_size', 10))
    if req_body.get('alias', None):
        results = azul_match_alias(index=INDEXES['data_bdl'],
                                   alias=req_body['alias'], size=per_page + 1,
                                   from_=page_token if page_token != 0 else None)
    else:
        results = es_query(query={}, index=INDEXES['data_bdl'], size=per_page + 1)

    if len(results) > per_page:
        next_page_token = str(int(page_token) + 1)
    else:
        next_page_token = None
    data_objects = map(azul_to_bdl, results)
    response = {'data_bundles': data_objects[0:per_page]}
    if next_page_token:
        response['next_page_token'] = next_page_token
    return response


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
        return Response({'msg': 'Not authorized to access this service. '
                                'Did you set access_token in the request'
                                ' headers?'}, status_code=403)

    # First try to get the Object specified
    try:
        source = azul_match_field(index=INDEXES['data_obj'], key='file_id', val=data_object_id)
    except LookupError:
        return Response({'msg': "Data object not found."}, status_code=404)
    data_object = azul_to_obj(source)

    # Now check to see the contents don't already contain
    # any aliases we want to add.

    if app.current_request.json_body:
        update_body = app.current_request.json_body
    else:
        return Response({'msg': 'Please add a data_object to the body of your request'},
                        status_code=400)

    if update_body.get('data_object', None):
        update_data_object = update_body['data_object']
    else:
        return Response({'msg': 'Please add a data_object to the body of your request'},
                        status_code=400)

    new_aliases = filter(
        lambda x: x not in data_object['aliases'],
        update_data_object['aliases'])
    # if len(new_aliases) == 0:
    #     return Response(
    #         {'msg': 'No new aliases, nothing was changed. '
    #                 'Please check your request details.'}, status_code=400)

    data_object['aliases'] = data_object['aliases'] + new_aliases

    es_id = source['_id']
    updated_fields = {'aliases': update_data_object['aliases']}

    path = '/{}/{}/{}/_update'.format(INDEXES['data_obj'], DOCTYPES['data_obj'], es_id)
    es_update_response = client.make_request(method='POST', path=path,
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
