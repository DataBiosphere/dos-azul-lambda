# dos-azul-lambda

[![Build Status](https://travis-ci.org/DataBiosphere/dos-azul-lambda.svg?branch=master)](https://travis-ci.org/DataBiosphere/dos-azul-lambda)

This presents an [Amazon Lambda](https://aws.amazon.com/lambda/) microservice
following the [Data Object Service](https://github.com/ga4gh/data-object-service-schemas) ([view the OpenAPI description](https://ga4gh.github.io/data-object-service-schemas/)!).
It allows data in the [Human Cell Atlas Data Store](https://github.com/HumanCellAtlas/data-store)
to be accessed using Data Object Service APIs.

## Using the service

```
+------------------+      +---------------+        +-----------+
| ga4gh-dos-client |------|dos-azul-lambda|--------|azul-index |
+--------|---------+      +---------------+        +-----------+
         |                        |
         |                        |
         |------------------swagger.json
```


A development version of this service is available at https://5ybh0f5iai.execute-api.us-west-2.amazonaws.com/api/ .
To make proper use of the service, one can either use cURL or an HTTP client to write API requests
following the [OpenAPI description](https://5ybh0f5iai.execute-api.us-west-2.amazonaws.com/api/swagger.json).

```
# Will request the first page of Data Bundles from the service.
curl -X GET --header 'Content-Type: application/json' --header 'Accept: application/json' https://iub0o6mnng.execute-api.us-west-2.amazonaws.com/dev/ga4gh/dos/v1/dataobjects
```

There is also a Python client available, that makes it easier to use the service from code.

```
from ga4gh.dos.client import Client
client = Client("https://5ybh0f5iai.execute-api.us-west-2.amazonaws.com/api")
local_client = client.client
local_client.ListDataBundles().result()
```

For more information refer to the [Data Object Service](https://github.com/ga4gh/data-object-service-schemas).

### Status

dos-azul-lambda is tested against Python 2.7 and Python 3.6.

This software is being actively developed to provide basic access to listing of
Data Objects made available by the dss-azul-indexer.

It also presents an area to explore features that allow DSS data to be resolved
by arbitrary provided metadata. Current development items can be seen in [the Issues](https://github.com/DataBiosphere/dos-azul-lambda/issues).

### Feature development

The Data Object Service can present many of the features of the DSS API naturally. This
lambda should present a useful client for the latest releases of the DSS API.

In addition, the DOS schemas may be extended to present available from the DSS, but
not from DOS.

#### DSS Features

* Subscriptions
* Authentication
* Querying
* Storage management

#### DOS Features

* File listing
  *  The DSS API presents bundle oriented indices that are not present in the dos-azul-index.
* Filter by URL
  *  Retrieve Data Objects by url, will require the dss-azul mapping to allow nested search.

### Installing and Deploying

The gateway portion of the AWS Lambda microservice is provided by chalice. So to manage
deployment and to develop you'll need to install chalice.

Once you have installed chalice, you can download and deploy your own version of the
service.

```
pip install chalice
git clone https://github.com/DataBiosphere/dos-azul-lambda.git
cd dos-azul-lambda
```

Then, edit the `.chalice/config.json` to use the instance of the azul-index you would like to use.

Here is an example config.json

```
{
  "version": "2.0",
  "app_name": "dos-azul-lambda",
  "stages": {
    "dev": {
      "api_gateway_stage": "api",
      "environment_variables": {
         "ES_HOST": "search-dss-azul-commons-lx3ltgewjw5wiw2yrxftoqr7jy.us-west-2.es.amazonaws.com",
         "ES_REGION": "us-west-2",
         "ES_INDEX": "fb_index",
         "ACCESS_KEY": "<YOUR_ACCESS_KEY>"
         "HOME":"/tmp"
      }
    }
  }
}
```

Note the environment variables, which are passed to the application. The `ACCESS_KEY`
should be a hard to guess string of letters and numbers. When requests to modify
an index are made, this value is checked for in the `access_key` header of the request.
Also note `ES_HOST` - this is the only mandatory variable. Without it, the lambda will
not run.

Then, create a file `.chalice/policy-dev.json` so it can access you azul index, assuming its
permissions have been set to allow it.

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Action": [
                "es:ESHttpDelete",
                "es:ESHttpGet",
                "es:ESHttpHead",
                "es:ESHttpPost",
                "es:ESHttpPut"
            ],
            "Effect": "Allow",
            "Resource": "*"
        }
    ]
}
```

You can then run `chalice deploy --staging commonsstaging --no-autogen-policy`.

Or, deploy to a specific AWS API Gateway stage, run:
`chalice deploy --no-autogen-policy --staging <stagename>`

Chalice will return a HTTP location that you can issue DOS requests to! You can then use
HTTP requests in the style of the [Data Object Service](https://ga4gh.github.io/data-object-service-schemas).

Finally, make sure the your DOS lambda has access to the dos-azul-index by editing its access policy.
If you need directions on how to setup the dos-azul-index, you can follow the directions in [here](https://github.com/DataBiosphere/cgp-dss-azul-indexer/tree/feature/commons)

You can also run the application locally with `chalice local` and run tests with `nosetests`.

#### Running Tests

Some integration tests are available in the `tests/` directory. To run them, you need to
spin up a new ElasticSearch domain on AWS. This is because data bundles are not currently
included in the default ElasticSearch index, and to ensure that tests can run in a clean,
isolated, and controlled environment. (See [`provision/README`](provision/README) for more details.)

First, install the development requirements:

    $ pip install -r dev-requirements.txt

Next, use `provision/provision.py` to start a new ElasticSearch instance. (You must
have AWS credentials configured, i.e. `aws configure`.)

    $ python provision/provision.py setup

The above command will take about ten minutes to complete. Once it's done, you'll
see an ElasticSearch domain name - something like `dos-azul-test-a1b2c3d4`. Copy
the domain name and use it to retrieve the ElasticSearch endpoint:

    $ # Substitute your domain below
    $ python provision/provision.py get-endpoint dos-azul-test-a1b2c3d4
    http://search-dos-azul-test-a1b2c3d4-hiybbprqag.us-west-2.es.amazonaws.com

Take the endpoint URL, strip the leading `http://` or `https://`, and set that as
the `ES_HOST` environment variable:

    $ export ES_HOST=search-dos-azul-test-a1b2c3d4-hiybbprqag.us-west-2.es.amazonaws.com

Finally, populate your new ES domain with data:

    $ python provision/provision.py populate dos-azul-test-a1b2c3d4

You can now run the unit tests:

    $ nosetests

If you want to run tests on a clean set of data, wipe the data then add the data again:

    $ python provision/provision.py raze dos-azul-test-a1b2c3d4
    $ python provision/provision.py populate dos-azul-test-a1b2c3d4

Tests should always pass on master. If they don't seem to be passing, make sure that
* your AWS credentials are set up properly
* you followed the instructions in [`provision/README`](provision/README)
* you set the `ES_HOST` environment variable properly

When you're done, use your ElasticSearch domain name (the short one) to tear down the
domain you created:

    $ python provision/provision.py teardown dos-azul-test-a1b2c3d4


#### Configuration

dos-azul-lambda can be configured by setting a number of environment variables:

* Set `DATA_OBJ_INDEX` to override the name of the ElasticSearch index to query
  for data objects. By default, this is `fb_index`.
* Set `DATA_BDL_INDEX` to override the name of the ElasticSearch index to query
  for data bundles. By default, this is `db_index`.
* Set `DATA_OBJ_DOCTYPE` to override the name of the ElasticSearch document type
  that dos-azul-lambda should expect to correspond with `DATA_OBJ_INDEX`. By
  default, this is `meta`.
* Set `DATA_BDL_DOCTYPE` to override the name of the ElasticSearch document type
  that dos-azul-lambda should expect to correspond with `DATA_BDL_INDEX`. By
  default, this is `databundle`.
* Set `ES_HOST` to specify the hostname of the ElasticSearch instance. **This
  must be manually set.** The endpoint should be specified without a leading
  protocol (e.g. `search-es-instance-12345.us-west-2.es.amazonaws.com`).
  By default, on live deployments of dos-azul-lambda, `ES_HOST` points to
  `dss-azul-commons` (when deployed via `chalice` - see `.chalice/config.json`).
  (Note that you shouldn't run tests against `dss-azul-commons` as is - see #102.)
* Set `ES_REGION` to override the default AWS region of the ElasticSearch
  instance. By default, this is `us-west-2`.
* Set `ACCESS_KEY` to override the default access token used to authenticate to
  dos-azul-lambda.
* Set `DEBUG` to `True` or `False` to enable or disable debug mode.


### Accessing data using DOS client

A Python client for the Data Object Service is made available [here](https://github.com/ga4gh/data-object-service-schemas/blob/master/python/ga4gh/dos/client.py).
Install this client and then view the example in [Example Usage](https://github.com/DataBiosphere/dos-azul-lambda/blob/master/example-usage.ipynb).
This notebook will guide you through basic read access to data in the DSS via DOS.

### Issues

If you have a problem accessing the service or deploying it for yourself, please head
over to [the Issues](https://github.com/DataBiosphere/dos-azul-lambda/issues) to let us know!

### Release strategy

Releases are marked with a GitHub Release and a tagged commit in the format `x.y.z`. (Travis won't
pick up a tagged commit with any other format.) Releases are made consistent with [Semantic Versioning](https://semver.org)
(though that also means that until a 1.0.0 release is made, most of the rules of semantic versioning
don't apply).

At the time of writing, releases are made available like so:
 
* Each commit triggers a deployment to https://dos.commons.ucsc-cgp-dev.org/ga4gh/dos/v1/,
  the bleeding-edge dev deployment.
* Each tagged release triggers a deployment to https://a4m3r21xx5.execute-api.us-west-2.amazonaws.com/ga4gh/dos/v1,
  the slightly-less-bloody-edge staging deployment. (No custom domain yet, sorry.)
* The production endpoint, available at https://dos.commons.ucsc-cgp.org/ga4gh/dos/v1,
  is maintained manually.

Deployments are managed by Travis in [.travis.yml](.travis.yml).
