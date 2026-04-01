import sys
import base64
import binascii
import json

PY3 = sys.version_info[0] == 3


if PY3:
    text_type = str
    binary_type = bytes
else:
    text_type = unicode
    binary_type = str

try:
    # Importing ABCs from collections will be removed in PY3.8
    from collections.abc import Iterable, Mapping
except ImportError:
    from collections import Iterable, Mapping


def jwt_decode(token):
    """
    Vendored code from jwt.decode.
    :param token:
    :type token: str
    :return: Decoded jwt dict.
    :rtype: dict
    """
    payload, _, _, _ = _jwt_load_vendored(token)

    payload = json.loads(payload.decode('utf-8'))
    if not isinstance(payload, Mapping):
        raise ValueError('Invalid payload string: must be a json object')
    return payload


def _jwt_load_vendored(token):
    if isinstance(token, text_type):
        token = token.encode('utf-8')

    if not issubclass(type(token), binary_type):
        raise ValueError("Invalid token type. Token must be a {0}".format(binary_type))

    try:
        signing_input, crypto_segment = token.rsplit(b'.', 1)
        header_segment, payload_segment = signing_input.split(b'.', 1)
    except ValueError:
        raise ValueError('Not enough segments')

    try:
        header_data = _base64url_decode(header_segment)
    except (TypeError, binascii.Error):
        raise ValueError('Invalid header padding')

    try:
        header = json.loads(header_data.decode('utf-8'))
    except ValueError as e:
        raise ValueError('Invalid header string: %s' % e)

    if not isinstance(header, Mapping):
        raise ValueError('Invalid header string: must be a json object')

    try:
        payload = _base64url_decode(payload_segment)
    except (TypeError, binascii.Error):
        raise ValueError('Invalid payload padding')

    try:
        signature = _base64url_decode(crypto_segment)
    except (TypeError, binascii.Error):
        raise ValueError('Invalid crypto padding')

    return payload, signing_input, header, signature


def _base64url_decode(to_decode):
    if isinstance(to_decode, text_type):
        to_decode = to_decode.encode('ascii')

    rem = len(to_decode) % 4

    if rem > 0:
        to_decode += b'=' * (4 - rem)

    return base64.urlsafe_b64decode(to_decode)
