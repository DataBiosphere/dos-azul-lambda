The purpose of `provision/provision.py` is to set up a copy of dss-azul-commons
that can be used to run dos-azul-lambda integration tests. Because spinning up
an ElasticSearch domain takes a while, the strategy that we've adopted is to
retain a single ElasticSearch domain, but to erase its contents and repopulate
it as needed. The ElasticSearch domain that is used is specified in `.travis.yml`.

To set up a new domain:

    python provision.py setup

To populate it:

    python provision.py populate <es_domain>

To erase it:

    python provision.py raze <es_domain>

To destroy the domain:

    python provision.py teardown <es_domain>

