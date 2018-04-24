# dos-azul-lambda

This presents an [Amazon Lambda](https://aws.amazon.com/lambda/) microservice
following the [Data Object Service](https://github.com/ga4gh/data-object-service-schemas) ([view the OpenAPI description](https://ga4gh.github.io/data-object-service-schemas/)!).
It allows data in the [Human Cell Atlas Data Store](https://github.com/HumanCellAtlas/data-store)
to be accessed using Data Object Service APIs.

## Using the service

A development version of this service is available at https://spbnq0bc10.execute-api.us-west-2.amazonaws.com/api/ .
To make proper use of the service, one can either use cURL or an HTTP client to write API requests
following the [OpenAPI description](https://spbnq0bc10.execute-api.us-west-2.amazonaws.com/api/swagger.json).

```
# Will request the first page of Data Bundles from the service.
curl -X POST --header 'Content-Type: application/json' --header 'Accept: application/json' -d '{}' 'https://spbnq0bc10.execute-api.us-west-2.amazonaws.com/api/ga4gh/dos/v1/databundles/list'
```

There is also a Python client available, that makes it easier to use the service from code.

```
from ga4gh.dos.client import Client
client = Client("https://spbnq0bc10.execute-api.us-west-2.amazonaws.com/api")
local_client = client.client
models = client.models
local_client.ListDataBundles(body={}).result()
```

For more information refer to the [Data Object Service](https://github.com/ga4gh/data-object-service-schemas).

## Development

### Status

This software is being actively developed to provide the greatest level of feature parity
between DOS and DSS. It also presents an area to explore features that might extend the DOS
API. Current development items can be seen in [the Issues](https://github.com/DataBiosphere/dos-azul-lambda/issues).

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
  *  The DSS API presents bundle oriented indices and so listing all the details of files
     can be a challenge.
* Filter by URL
  *  Retrieve bundle entries by their URL to satisfy the DOS List request.

### Installing and Deploying

The gateway portion of the AWS Lambda microservice is provided by chalice. So to manage
deployment and to develop you'll need to install chalice.

Once you have installed chalice, you can download and deploy your own version of the
service.

```
pip install chalice
git clone https://github.com/DataBiosphere/dos-azul-lambda.git
cd dos-azul-lambda
chalice deploy
```

Chalice will return a HTTP location that you can issue DOS requests to. You can then use
HTTP requests in the style of the [Data Object Service](https://ga4gh.github.io/data-object-service-schemas).

### Accessing data using DOS client

A Python client for the Data Object Service is made available [here](https://github.com/ga4gh/data-object-service-schemas/blob/master/python/ga4gh/dos/client.py).
Install this client and then view the example in [Example Usage](https://github.com/DataBiosphere/dos-azul-lambda/blob/master/example-usage.ipynb).
This notebook will guide you through basic read access to data in the DSS via DOS.

### Issues

If you have a problem accessing the service or deploying it for yourself, please head
over to [the Issues](https://github.com/DataBiosphere/dos-azul-lambda/issues) to let us know!


## TODO

* Validation
* Error handling
* Aliases
* Filter by URL

```                                                                                         
+------------------+      +---------------+        +--------+
| ga4gh-dos-client |------|dos-azul-lambda|--------|DSS API |
+--------|---------+      +---------------+        +--------+
         |                        |                                                         
         |                        |                                                         
         |------------------swagger.json                                                    
```

We have created a lambda that creates a lightweight layer that can be used
to access data in the HCA DSS using GA4GH libraries.

The lambda accepts DOS requests and converts them into requests against
DSS endpoints. The results are then translated into DOS style messages before
being returned to the client.

To make it easy for developers to create clients against this API, the Open API
description is made available.


