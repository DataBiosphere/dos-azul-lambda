# -*- coding: utf-8 -*-
# The dos-azul-lambda request handling stack is generally structured like so:
#
#      /\  * Endpoint handlers, named for the DOS operation converted to
#     /__\   snake case (e.g. list_data_bundles).
#    /    \  * ElasticSearch helper functions that implement common query types
#   /______\   such as matching on a certain field, with names matching `azul_*`
#  /________\  * The ElasticSearch bindings.
#
# Error catching should be handled as follows:
# * Functions that return :class:`~chalice.Response` objects should raise
#   Chalice exceptions where appropriate. Chalice exceptions will halt
#   control flow and return a response with an appropriate error code and
#   a nice message.
# * Functions that don't return :class:`~chalice.Response` objects should
#   raise builtin exceptions where appropriate. Those exceptions should be
#   caught by the aforementioned and either ignored or replaced with Chalice
#   exceptions.
# * Endpoint handlers should raise exceptions consistent with the DOS schema.
# * Between all of this, exception logging should occur at the lowest level,
#   next to where an exception is raised.
import datetime
import logging
import os

import aws_requests_auth.aws_auth
import boto3.session
from chalice import Chalice, Response, BadRequestError, UnauthorizedError, \
    NotFoundError, ChaliceViewError
import elasticsearch
import ga4gh.dos.client
import ga4gh.dos.schema
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('dos-azul-lambda')

# We only need the client for the models, so we can provide any URL
dos_client = ga4gh.dos.client.Client(url='https://example.com/abc', local=True)


def model(model_name, **kwargs):
    return dos_client.models.get_model(model_name)(**kwargs)


def parse_azul_date(azul_date):
    """
    :rtype: datetime.datetime
    """
    # Process the string first to account for inconsistencies in date storage in Azul
    date = azul_date.rstrip('Z').replace(':', '') + 'Z'
    date = datetime.datetime.strptime(date, '%Y-%m-%dT%H%M%S.%fZ')
    return date.replace(tzinfo=pytz.utc)


def azul_to_obj(result):
    """
    Takes an Azul ElasticSearch result and converts it to a DOS data
    object.

    :param result: the ElasticSearch result dictionary
    :rtype: DataObject
    """
    azul = result['_source']
    data_object = model(
        model_name='DataObject',
        id=azul['file_id'],
        name=azul['title'],
        size=str(azul.get('fileSize', '')),
        created=parse_azul_date(azul['lastModified']),
        updated=parse_azul_date(azul['lastModified']),
        version=azul['file_version'],
        checksums=[model('Checksum', checksum=azul['fileMd5sum'], type='md5')],
        urls=[model('URL', url=url) for url in azul['urls']],
        aliases=azul['aliases'],
    )
    return data_object


def obj_to_azul(data_object):
    """
    Takes a data object and converts it to an Azul object.
    :rtype: dict
    """
    # updated is optional but created is not
    date = data_object.get('updated', data_object['created']).replace(':', '')
    date = datetime.datetime.strptime(date, '%Y-%m-%dT%H%M%S.%f+0000')
    date = date.replace(tzinfo=pytz.utc)
    date = date.strftime('%Y-%m-%dT%H%M%S.%fZ')
    checksum = data_object['checksums'][0]
    azul = {
        'file_id': data_object['id'],
        'title': data_object.get('name', ''),  # name is optional
        'fileSize': data_object.get('size', ''),
        'lastModified': date,
        'file_version': data_object.get('version'),
        'fileMd5sum': checksum['checksum'] if checksum['type'] == 'md5' else '',
        'urls': [url['url'] for url in data_object['urls']],
        'aliases': data_object.get('aliases'),  # aliases are optional
    }
    return azul


def azul_to_bdl(result):
    """
    Takes an Azul ElasticSearch result and converts it to a DOS data
    bundle.

    :param result: the ElasticSearch result dictionary
    :return: DataBundle
    """
    azul = result['_source']
    data_bundle = model(
        model_name='DataBundle',
        id=azul['id'],
        data_object_ids=azul['data_object_ids'],
        created=parse_azul_date(azul['created']),
        updated=parse_azul_date(azul['updated']),
        version=azul['version'],
        description=azul.get('description', ''),  # optional field
        aliases=azul.get('aliases', ''),  # optional field
    )
    data_bundle.checksums = []
    for checksum in azul['checksums']:
        checksum, checksum_type = checksum.split(':', 1)
        data_bundle.checksums.append(model('Checksum', checksum=checksum, type=checksum_type))

    return data_bundle


def check_auth():
    """
    Execute during a request to check the ``access_token`` key in the
    request headers.
    :return: True if ``access_token`` is valid, False otherwise
    :rtype: bool
    """
    return app.current_request.headers.get('access_token', None) == access_token


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

try:
    es_host = os.environ['ES_HOST']
except KeyError:
    raise RuntimeError("You must specify the domain name of your ElasticSearch"
                       " instance with the ES_HOST environment variable.")
es_region = os.environ.get('ES_REGION', DEFAULT_REGION)
access_token = os.environ.get('ACCESS_KEY', DEFAULT_ACCESS_TOKEN)

session = boto3.session.Session()
credentials = session.get_credentials().get_frozen_credentials()
awsauth = aws_requests_auth.aws_auth.AWSRequestsAuth(
    aws_access_key=credentials.access_key,
    aws_secret_access_key=credentials.secret_key,
    aws_token=credentials.token,
    aws_host=es_host,
    aws_region=session.region_name,
    aws_service='es'
)
es = elasticsearch.Elasticsearch(
    hosts=[{'host': es_host, 'port': 443}],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=elasticsearch.RequestsHttpConnection
)
app = Chalice(app_name='dos-azul-lambda')
app.debug = os.environ.get('DEBUG', 'True') == 'True'

base_path = '/ga4gh/dos/v1'


@app.route('/', cors=True)
def index():
    return es.info()  # Returns a 2-tuple: (health info as JSON, status code)


@app.route('/test_token', methods=["GET", "POST"], cors=True)
def test_token():
    """
    A convenience endpoint for testing whether an access token
    is active or not. Will return a JSON with a key `authorized`
    and a boolean regarding the key's value.
    """
    body = {'authorized': check_auth()}
    return Response(body, status_code=200 if body['authorized'] else 401)


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
    results = es.search(index=index, size=size, body={'query': {'bool': {'must': {'term': {key: val}}}}})
    if len(results) < 1:
        # We don't need to log an exception here since this kind of error could
        # occur if a user requests a file that does not exist.
        raise LookupError("Query returned no results")
    return results['hits']['hits'][0]


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
    return es.search(index=index, size=size, from_=from_ or 0,  # short circuiting
                     body={'query': {'term': {'aliases.keyword': alias}}})['hits']['hits']


def azul_get_document(key, val, name, es_index, map_fn, model):
    """
    Queries ElasticSearch for a single document and returns a
    :class:`~chalice.Response` object with the retrieved data. Wrapper
    around :func:`azul_match_field`. Implements lookup functionality used
    in :func:`get_data_object` and :func:`get_data_bundle`.
    :param str key: the key to search for in the given ElasticSearch index
    :param str val: the value to search for in the given ElasticSearch index
    :param str name: the key the document should be returned under
    :param str es_index: the name of the index to query in ElasticSearch
    :param callable map_fn: function mapping the returned Azul document to a
                            DOS format
    :param model: DOS response model
    :raises RuntimeError: if the ElasticSearch response is not understood
    :rvtype: :class:`chalice.Response`
    :returns: the retrieved data or the error state
    """
    try:
        data = azul_match_field(index=es_index, key=key, val=val)
        data = map_fn(data)
        # Double check to verify identity
        if data['id'] != val:
            raise LookupError("ID mismatch in results")
    except LookupError:
        # azul_match_field will also raise a LookupError if no results are returned.
        # This isn't really an error, as a user requesting an object that could
        # not be found is generally not unexpected.
        raise NotFoundError("No results found for type %s and ID %s." % (name, val))
    except RuntimeError:
        # es_query will raise a RuntimeError if it doesn't understand the ES
        # response. It is logged in :func:`es_query`
        raise ChaliceViewError("Received an unexpected response from Azul.")
    except Exception:
        # If anything else happens...
        logger.exception("Unexpected error attempting to retrieve {name} "
                         "{key}={val} from index {es_index} using transformer"
                         " {fn}".format(name=name, key=key, val=val,
                                        es_index=es_index, fn=map_fn.func_name))
        raise ChaliceViewError("There was a problem communicating with Azul.")
    return Response(model(**{name: data}).marshal(), status_code=200)


@app.route(base_path + '/dataobjects/{data_object_id}', methods=['GET'], cors=True)
def get_data_object(data_object_id):
    """
    Gets a data object by file identifier by making a query against the
    configured data object index and returns the first matching file.

    :param data_object_id: the id of the data object
    :rtype: DataObject
    """
    return azul_get_document(key='file_id', val=data_object_id, name='data_object',
                             map_fn=azul_to_obj, es_index=INDEXES['data_obj'],
                             model=dos_client.models.get_model('GetDataObjectResponse'))


@app.route(base_path + '/databundles/{data_bundle_id}', methods=['GET'], cors=True)
def get_data_bundle(data_bundle_id):
    """
    Gets a data bundle by its identifier by making a query against the
    configured data bundle index. Returns the first matching file.

    :param data_bundle_id: the id of the data bundle
    :rtype: DataBundle
    """
    return azul_get_document(key='id', val=data_bundle_id, name='data_bundle',
                             map_fn=azul_to_bdl, es_index=INDEXES['data_bdl'],
                             model=dos_client.models.get_model('GetDataBundleResponse'))


@app.route(base_path + '/dataobjects', methods=['GET'], cors=True)
def list_data_objects(**kwargs):
    """
    Page through the data objects index and return data objects,
    respecting an alias or checksum request if it is made.

    :rtype: ListDataObjectsResponse
    """
    req_body = app.current_request.query_params or {}
    per_page = int(req_body.get('page_size', 10))

    # Build the query. If multiple criteria are specified, returned objects
    # should match all of the provided criteria (logical AND).
    query = {'query': {}, 'size': per_page + 1, 'index': INDEXES['data_obj']}
    if 'page_token' in req_body:  # for paging
        query['from_'] = req_body['page_token']
    if 'alias' in req_body or 'checksum' in req_body or 'url' in req_body:
        query['query']['bool'] = {'filter': []}
        # Azul only stores MD5s so there are no results if checksum_type != md5
        if 'checksum_type' in req_body and req_body['checksum_type'].lower() != 'md5':
            return {'data_objects': []}
        if 'alias' in req_body:
            query['query']['bool']['filter'].append({
                'term': {
                    'aliases.keyword': {'value': req_body['alias']}
                }
            })
        if 'checksum' in req_body:
            query['query']['bool']['filter'].append({
                'term': {
                    'fileMd5sum.keyword': {'value': req_body['checksum']}
                }
            })
        if 'url' in req_body:
            query['query']['bool']['filter'].append({
                'term': {
                    'urls.keyword': {'value': req_body['url']}
                }
            })
    else:  # if no query parameters are provided
        query['query']['match_all'] = {}
    query['body'] = {'query': query.pop('query')}
    results = es.search(**query)['hits']['hits']
    response = model('ListDataObjectsResponse')
    response.data_objects = [azul_to_obj(x) for x in results[:per_page]]
    if len(results) > per_page:
        response.next_page_token = str(int(req_body.get('page_token', 0)) + 1)
    return response.marshal()


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
        results = es.search(body={'query': {}}, index=INDEXES['data_bdl'],
                            size=per_page + 1)['hits']['hits']
    response = model('ListDataBundlesResponse')
    response.data_bundles = [azul_to_bdl(x) for x in results[:per_page]]
    if len(results) > per_page:
        response.next_page_token = str(int(page_token) + 1)
    return response.marshal()


@app.route(base_path + '/service-info', methods=['GET'], cors=True)
def get_service_info():
    return {"version": "0.4.0", "name" : "dos-azul-lambda", "description" : "This presents an Amazon Lambda microservice following the Data Object Service. It allows data in the Human Cell Atlas Data Store to be accessed using Data Object Service APIs."}


@app.route(base_path + '/dataobjects/{data_object_id}', methods=['PUT'], cors=True)
def update_data_object(data_object_id):
    """
    Updates a data object. The data object must exist.
    :param data_object_id: the id of the data object to update
    """
    # Ensure that the user is authenticated first
    if not check_auth():
        raise UnauthorizedError("You're not authorized to use this service. "
                                "Did you set access_token in the request headers?")

    # Make sure that the data object to update exists
    try:
        source = azul_match_field(index=INDEXES['data_obj'], key='file_id', val=data_object_id)
    except LookupError:
        raise NotFoundError("Data object not found.")

    # Check that a data object was provided in the request
    body = app.current_request.json_body
    if not body or not body.get('data_object', None):
        raise BadRequestError("Please add a data_object to the body of your request.")

    # Now that we know everything is okay, do the actual update
    data = {'doc': obj_to_azul(body['data_object'])}
    es.update(index=INDEXES['data_obj'], doc_type=DOCTYPES['data_obj'], id=source['_id'], body=data)
    return model('UpdateDataObjectResponse', data_object_id=data_object_id).marshal()


@app.route('/swagger.json', cors=True)
def swagger():
    """
    An endpoint for returning the Swagger API description.
    """
    swagger = ga4gh.dos.schema.from_chalice_routes(app.routes)
    swagger['basePath'] = '/api/ga4gh/dos/v1'
    return swagger

