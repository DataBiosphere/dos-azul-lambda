# dos-azul-lambda

<img src="https://travis-ci.org/DataBiosphere/dos-azul-lambda.svg?branch=master" />

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

Some integration tests are available in the tests directory.

```
pip install -r dev-requirements.txt
nosetests
```

Assuming your AWS credentials are set up properly to access the Elastic Search
domain, you will see a few tests pass that demonstrate the List and Get
features of the DOS endpoint.


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
* Set `ES_HOST` to override the hostname of the ElasticSearch instance. By
  default, this points to the `dss-azul-commons` ElasticSearch instance. This
  variable should be specified without the protocol (i.e. without a leading
  `http://` or `https://`).
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
