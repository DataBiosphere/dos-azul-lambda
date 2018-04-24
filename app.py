import os
import json

from chalice import Chalice
from boto.connection import AWSAuthConnection
import requests
import yaml


"""
            {
                "_id": "f4f437e8-dce2-4383-b99f-5d3da64e87a9.2018-02-28T054325.291177Z",
                "_index": "fb_index",
                "_score": 1.0,
                "_source": {
                    "access": "public",
                    "analysis_type": "alignment",
                    "center_name": "UW",
                    "donor": "2a65c602-fa66-5be2-9ccb-9387fd24f81e",
                    "download_id": "2e8505c4-8704-5f9f-ad6c-6fdeadbeb1d1",
                    "experimentalStrategy": "Seq_DNA_SNP_CNV; Seq_DNA_WholeGenome",
                    "fileMd5sum": "5d958276d8abdb4b0396700b741620e68714376b",
                    "fileSize": 1302863,
                    "file_id": "f4f437e8-dce2-4383-b99f-5d3da64e87a9",
                    "file_type": "crai",
                    "file_version": "2018-02-28T054325.291177Z",
                    "lastModified": "2018-02-22T06:32:18.841046",
                    "metadataJson": "",
                    "program": "NHLBI TOPMed: Genetic Epidemiology of COPD (COPDGene) in the TOPMed Program",
                    "project": "COPD",
                    "redwoodDonorUUID": "2a65c602-fa66-5be2-9ccb-9387fd24f81e",
                    "repoBaseUrl": "",
                    "repoCode": "Redwood-AWS-Oregon",
                    "repoCountry": "US",
                    "repoDataBundleId": "2e8505c4-8704-5f9f-ad6c-6fdeadbeb1d1",
                    "repoName": "Redwood-AWS-Oregon",
                    "repoOrg": "UCSC",
                    "repoType": "Blue Box",
                    "sampleId": "44488979-5660-578f-aaa8-d43d20e8552b",
                    "software": "topmed-spinnaker",
                    "specimenUUID": "d842b267-a154-5192-988b-b9f9f0265840",
                    "specimen_type": "Normal - Blood",
                    "study": "COPD",
                    "submittedDonorId": "COPDGene_R55698",
                    "submittedSampleId": "NWD230469",
                    "submittedSpecimenId": "SRS1235045",
                    "submitterDonorPrimarySite": "Blood",
                    "submitter_donor_id": "",
                    "title": "NWD230469.b38.irc.v1.cram.crai",
                    "urls": [
                        "s3://nih-nhlbi-datacommons/NWD230469.b38.irc.v1.cram.crai",
                        "gs://topmed-irc-share/genomes/NWD230469.b38.irc.v1.cram.crai"
                    ],
                    "workflow": "topmed-spinnaker:Alpha Build 1",
                    "workflowVersion": "Alpha Build 1"
                }

"""

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
    data_object['checksums'] = [{'checksum': azul['fileMd5sum'], 'type': 'md5'}]
    # remove multiply valued items before we move into aliases
    del azul['urls']
    data_object['aliases'] = ["{}:{}".format(k, azul[k]) for k in azul.keys()]
    data_object['updated'] = azul['lastModified']
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

# Ensure that you set 'host' below to the FQDN for YOUR Elasticsearch service endpoint
es_index = os.environ.get('ES_INDEX', 'azul-test-indexer')
es_host = os.environ.get('ES_HOST', 'search-dss-azul-commons-lx3ltgewjw5wiw2yrxftoqr7jy.us-west-2.es.amazonaws.com')
es_region = os.environ.get('ES_REGION', 'search-dss-azul-commons-lx3ltgewjw5wiw2yrxftoqr7jy.us-west-2.es.amazonaws.com')
client = ESConnection(region=es_region, host=es_host, is_secure=False)
app = Chalice(app_name='dos-azul-lambda')
app.debug = True

base_path = '/ga4gh/dos/v1'

@app.route('/', cors=True)
def index():
    resp = client.make_request(method='GET', path='/')
    return resp.read()

@app.route("{}/dataobjects/list".format(base_path), methods=['POST'], cors=True)
def list_data_objects(**kwargs):
    """
    Page through the es_index and return data objects, respecting an
    alias or checksum request if it is made.

    :param kwargs:
    :return: ListDataObjectsResponse
    """
    req_body = app.current_request.json_body
    per_page = 10
    page_token = 0
    if req_body and (req_body.get('page_size', None)):
        per_page = req_body.get('page_size')
    if req_body and (req_body.get('page_token', None)):
        page_token = req_body.get('page_token')
    query = {'size': per_page}
    if page_token:
        query['from'] = page_token
    if req_body and req_body.get('alias', None):
        # We kludge on our own tag scheme
        alias = req_body.get('alias')
        k, v = alias.split(":")
        query['query'] = {'match': {k: v}}
    next_page_token = str(int(page_token) + 1)
    resp = client.make_request(method='GET', path='/{}/_search'.format(es_index), data=json.dumps(query))
    try:
        hits = json.loads(resp.read())['hits']['hits']
    except Exception as e:
        return {"resp": resp.read(), "exception": str(e)}
    data_objects = map(lambda x: azul_to_dos(x['_source']), hits)
    return {'data_objects': data_objects, 'next_page_token': next_page_token}

@app.route('/swagger.json', cors=True)
def swagger():
    """
    An endpoint for returning the swagger api description.

    :return:
    """
    # FIXME replace with one hosted here
    req = requests.get("https://ga4gh.github.io/data-object-service-schemas/swagger/data_object_service.swagger.yaml")
    swagger_dict = yaml.load(req.content)

    swagger_dict['basePath'] = '/api/ga4gh/dos/v1'
    return swagger_dict