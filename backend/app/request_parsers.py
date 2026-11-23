"""Capture parameter names during ordinary DRF parsing, without retaining values."""
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser


def remember_names(context, *groups):
    request = (context or {}).get("request")
    if request is None:
        return
    names = set()
    for group in groups:
        if hasattr(group, "keys"):
            names.update(str(key)[:80] for key in group.keys())
    request._request._access_parameter_names = sorted(names)[:50]


class AccessJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        remember_names(parser_context, data)
        return data


class AccessFormParser(FormParser):
    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        remember_names(parser_context, data)
        return data


class AccessMultiPartParser(MultiPartParser):
    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        remember_names(parser_context, data.data, data.files)
        return data
