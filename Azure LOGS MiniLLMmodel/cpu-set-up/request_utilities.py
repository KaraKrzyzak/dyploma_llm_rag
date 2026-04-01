import azureml_globals

try:
    # For Python 3.0 and later
    from urllib.request import urlopen, Request
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import urlopen, Request


def send_request(url, data=None, headers=None, method=None):
    args = {"url": url}
    if data:
        args['data'] = data.encode('utf8')
    if headers:
        args['headers'] = headers
    if method:
        # the default is GET if data is None, POST otherwise
        args["method"] = method

    return urlopen(Request(**args), timeout=5)


def get_service_url(service_name):
    return azureml_globals.service_endpoint + "/" + service_name + "/v1.0"


def get_telemetry_url(batch=False):
    url = get_service_url("execution") + azureml_globals.experiment_scope + "/runs/" + \
        azureml_globals.run_id + "/telemetry"
    if batch:
        url += "/batch"
    return url


def get_default_headers(token, content_type=None, read_bytes=None):
    headers = {"Authorization": "Bearer %s" % token}

    if content_type:
        headers['Content-Type'] = content_type

    if read_bytes:
        headers['Content-Length'] = '%d' % len(read_bytes)

    return headers
