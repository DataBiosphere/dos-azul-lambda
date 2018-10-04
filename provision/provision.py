# -*- coding: utf-8 -*-
"""
$ provision/provision.py {setup,teardown,populate,raze} <domain>

Domain is in the format short-name-here and NOT https://search-short-name-here-...
"""
import json
import logging
import os
import string
import sys
import time

import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
aws = boto3.client('es')

# Get index names
obj_index = os.environ.get('DATA_OBJ_INDEX', 'fb_index')
bdl_index = os.environ.get('DATA_BDL_INDEX', 'db_index')


def getpath(filename):
    return os.path.abspath(os.path.join(os.path.dirname(__file__), filename))


def get_endpoint(es_domain):
    """
    Finds the endpoint (that requests should be made to) for a given
    ElasticSearch domain.

    :rtype: string
    """
    backoff = 0
    status = {}
    while not status.get('DomainStatus', {}).get('Endpoint', None):
        status = aws.describe_elasticsearch_domain(DomainName=es_domain)
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
    return 'https://' + status['DomainStatus']['Endpoint']


def populate_domain(endpoint):
    """
    Given an ElasticSearch endpoint, populates the domain with a
    'faithful' replica of dss-azul-commons for testing purposes.
    """
    # Set up indexes
    with open(getpath('index-mapping.json'), 'r') as data:
        index_cfg = json.load(data)
    es.indices.create(index=obj_index, body=json.dumps(index_cfg['fb_index']))
    es.indices.create(index=bdl_index, body=json.dumps(index_cfg['db_index']))

    # Populate both indexes
    with open(getpath('test-data.json'), 'r') as data:
        # Make sure that documents are uploaded to correct index if index
        # name has been changed
        payload = string.Template(data.read()).substitute({
            'data_obj': obj_index,
            'data_bdl': bdl_index
        })
        es.bulk(body=payload)


def raze_domain(endpoint):
    """
    Given an ElasticSearch endpoint, drops fb_index and db_index so that
    it can be populated anew.
    """
    # Drop indexes
    es.indices.delete(index=obj_index)
    es.indices.delete(index=bdl_index)


def setup(es_domain):
    """
    Sets up an ElasticSearch domain.
    """
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
    aws.create_elasticsearch_domain(
        DomainName=es_domain,
        ElasticsearchVersion='5.5',
        ElasticsearchClusterConfig={
            'InstanceType': 't2.small.elasticsearch',
            'InstanceCount': 1,
            'DedicatedMasterEnabled': False,
            'ZoneAwarenessEnabled': False,
        },
        EBSOptions={  # required for t2.small.elasticsearch
            'EBSEnabled': True,
            'VolumeType': 'standard',  # st1 is cheaper but not supported
            'VolumeSize': 10,  # minimum for t2.small.elasticsearch
        },
        AccessPolicies=policy,
        CognitoOptions={'Enabled': False},
        EncryptionAtRestOptions={'Enabled': False},
    )
    return es_domain


def teardown(es_domain):
    aws.delete_elasticsearch_domain(DomainName=es_domain)


if __name__ == '__main__':
    _, command, domain = sys.argv
    # All commands require an endpoint except for `setup`, so check for
    # that first. (`setup` still requires a domain to name the ElasticSearch
    # instance that will be created.)
    if command == 'setup':
        # Create a new domain
        es_domain = setup(es_domain=domain)
        # We need to wait for the instance to spin up before we can do anything
        # with it. This is the long part - Amazon says it takes about ten minutes.
        logger.info("Waiting for the ElasticSearch domain to become available.")
        logger.info("This takes about ten minutes...")
        time.sleep(60 * 7)
        get_endpoint(es_domain)
        sys.stdout.write(es_domain)
        exit(0)
    # We check to make sure that the command exists before importing the
    # ElasticSearch client in case no domain has been provided
    elif command not in ['teardown', 'populate', 'raze', 'get-endpoint']:
        print(__doc__)
        raise RuntimeError("Unknown command")

    # If we are here, an endpoint should exist, so we can set up the
    # ElasticSearch client
    endpoint = get_endpoint(domain)
    sys.path.insert(0, getpath('..'))
    os.environ['ES_HOST'] = endpoint.replace('http://', '').replace('https://', '')
    from app import es

    if command == 'teardown':
        teardown(domain)
    elif command == 'populate':
        populate_domain(get_endpoint(sys.argv[2]))
    elif command == 'raze':
        raze_domain(get_endpoint(sys.argv[2]))
    elif command == 'get-endpoint':
        sys.stdout.write(get_endpoint(sys.argv[2]))
