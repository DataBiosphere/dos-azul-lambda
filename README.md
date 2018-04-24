# dos-azul-lambda

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


A development version of this service is available at https://spbnq0bc10.execute-api.us-west-2.amazonaws.com/api/ .
To make proper use of the service, one can either use cURL or an HTTP client to write API requests
following the [OpenAPI description](https://5ybh0f5iai.execute-api.us-west-2.amazonaws.com/api/swagger.json).

```
# Will request the first page of Data Bundles from the service.
curl -X POST --header 'Content-Type: application/json' --header 'Accept: application/json' -d '{}' 'https://5ybh0f5iai.execute-api.us-west-2.amazonaws.com/api/ga4gh/dos/v1/dataobjects/list'
```

There is also a Python client available, that makes it easier to use the service from code.

```
from ga4gh.dos.client import Client
client = Client("https://5ybh0f5iai.execute-api.us-west-2.amazonaws.com/api")
local_client = client.client
models = client.models
local_client.ListDataBundles(body={}).result()
```

For more information refer to the [Data Object Service](https://github.com/ga4gh/data-object-service-schemas).

## Development

### Status

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
         "ES_INDEX":"fb_index",
         "HOME":"/tmp"
      }
    }
  }
}
```

Then, create a file `.chalice/policy-dev.json` so it can access you azul index, assuming its
permissions have been set to allow it.

```
{
    "Version": "2012-10-17",
    "Statement": [
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

You can then run `chalice deploy --no-autogen-policy`.

Chalice will return a HTTP location that you can issue DOS requests to! You can then use
HTTP requests in the style of the [Data Object Service](https://ga4gh.github.io/data-object-service-schemas).

### Accessing data using DOS client

A Python client for the Data Object Service is made available [here](https://github.com/ga4gh/data-object-service-schemas/blob/master/python/ga4gh/dos/client.py).
Install this client and then view the example in [Example Usage](https://github.com/DataBiosphere/dos-azul-lambda/blob/master/example-usage.ipynb).
This notebook will guide you through basic read access to data in the DSS via DOS.

### Issues

If you have a problem accessing the service or deploying it for yourself, please head
over to [the Issues](https://github.com/DataBiosphere/dos-azul-lambda/issues) to let us know!
