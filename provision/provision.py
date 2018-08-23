# -*- coding: utf-8 -*-
"""
$ provision/provision.py {setup,teardown,populate,raze} <domain>
"""
import json
import logging
import os
import string
import sys
import time
import uuid

import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
es = boto3.client('es')

# Get index names
obj_index = os.environ.get('DATA_OBJ_INDEX', 'fb_index')
bdl_index = os.environ.get('DATA_BDL_INDEX', 'db_index')


def getpath(filename):
    return os.path.abspath(os.path.join(os.path.dirname(__file__), filename))


def get_request_handler(endpoint):
    sys.path.insert(0, getpath('..'))
    os.environ['ES_HOST'] = endpoint[7:]  # remove http://
    from app import make_es_request
    return make_es_request


def get_endpoint(es_domain):
    """
    Finds the endpoint (that requests should be made to) for a given
    ElasticSearch domain.

    :rtype: string
    """
    backoff = 0
    status = {}
    while not status.get('DomainStatus', {}).get('Endpoint', None):
        status = es.describe_elasticsearch_domain(DomainName=es_domain)
        # \sum_{n=0}^{9} 2^n is a long time and if there hasn't been a response
        # by then, one probably isn't coming anytime soon.
        if backoff > 10:
            raise RuntimeError("It's been a long time, and the ElasticSearch "
                               "domain still looks to be unavailable. It's "
                               "been long enough that I'm considering this "
                               "a timeout.")
        if not status['DomainStatus'].get('Endpoint', None):
            time.sleep(2 ** backoff)
            backoff += 1

    # boto3 returns the endpoint without the URL protocol, so we need
    # to add it if it doesn't exist, otherwise requests will choke
    return 'http://' + status['DomainStatus']['Endpoint']


def populate_domain(endpoint):
    """
    Given an ElasticSearch endpoint, populates the domain with a
    'faithful' replica of dss-azul-commons for testing purposes.
    """
    # boto3 can't sign requests by default, so we pull the boto2 request
    # handler from app.py (which is already nicely configured)
    make_es_request = get_request_handler(endpoint)

    # Set up fb_index (data_objects)
    with open(getpath('index-mapping.json'), 'r') as data:
        payload = json.load(data)['fb_index']
    make_es_request(method='PUT', path='/' + obj_index, data=json.dumps(payload))

    # Set up db_index (data bundles)
    with open(getpath('index-mapping.json'), 'r') as data:
        payload = json.load(data)['db_index']
    make_es_request(method='PUT', path='/' + bdl_index, data=json.dumps(payload))

    # Populate both indexes
    with open(getpath('test-data.json'), 'r') as data:
        # Make sure that documents are uploaded to correct index if index
        # name has been changed
        payload = string.Template(data.read()).substitute({
            'data_obj': obj_index,
            'data_bdl': bdl_index
        })
        make_es_request(method='POST', path='/_bulk', data=payload)


def raze_domain(endpoint):
    """
    Given an ElasticSearch endpoint, drops fb_index and db_index so that
    it can be populated anew.
    """
    # boto3 can't sign requests by default, so we pull the boto2 request
    # handler from app.py (which is already nicely configured)
    make_es_request = get_request_handler(endpoint)

    # Drop fb_index
    make_es_request(method='DELETE', path='/' + obj_index)

    # Drop db_index
    make_es_request(method='DELETE', path='/' + bdl_index)


def setup(es_domain=None):
    """
    Sets up an ElasticSearch domain.
    """
    if not es_domain:
        es_domain = 'dos-azul-test-' + str(uuid.uuid1()).split('-')[0]
    aws_info = boto3.client('sts').get_caller_identity()
    region = boto3.session.Session().region_name

    # Generate the policy from policy.json, filling in the blanks.
    with open(getpath('policy.json'), 'r') as ES_ACCESS_POLICY:
        policy = string.Template(ES_ACCESS_POLICY.read()).substitute({
            'aws_id': aws_info['Account'],
            'es_domain': es_domain,
            'user_arn': aws_info['Arn'],
            'region': region
        })
    es.create_elasticsearch_domain(
        DomainName=es_domain,
        ElasticsearchVersion='5.5',
        ElasticsearchClusterConfig={
            'InstanceType': 'i3.large.elasticsearch',
            'InstanceCount': 1,
            'DedicatedMasterEnabled': False,
            'ZoneAwarenessEnabled': False,
        },
        AccessPolicies=policy,
        CognitoOptions={'Enabled': False},
        EncryptionAtRestOptions={'Enabled': False},
    )
    return es_domain


def teardown(es_domain):
    es.delete_elasticsearch_domain(DomainName=es_domain)


if __name__ == '__main__':
    command = sys.argv[1]
    if command == 'teardown':
        teardown(sys.argv[2])
    elif command == 'setup':
        if len(sys.argv) > 3:
            domain = sys.argv[3]
        else:
            domain = None
        # Create a new domain
        es_domain = setup(es_domain=domain)

        # We need to wait for the instance to spin up before we can do anything
        # with it. This is the long part - Amazon says it takes about ten minutes.
        logger.info("Waiting for the ElasticSearch domain to become available.")
        logger.info("This takes about ten minutes...")
        time.sleep(60 * 7)
        get_endpoint(es_domain)
        sys.stdout.write(es_domain)
    elif command == 'populate':
        populate_domain(get_endpoint(sys.argv[2]))
    elif command == 'raze':
        raze_domain(get_endpoint(sys.argv[2]))
    elif command == 'get-endpoint':
        sys.stdout.write(get_endpoint(sys.argv[2]))
    else:
        raise RuntimeError("Unknown command")
