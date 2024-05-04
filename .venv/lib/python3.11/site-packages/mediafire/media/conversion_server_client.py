"""Conversion Server API"""
# Audio and Video transcoding URL is sent in response to file/get_links
# and only Image and Document conversion use conversion_server.php endpoint

from __future__ import unicode_literals

import logging
import requests

from six.moves.urllib.parse import urlencode

from mediafire.api import QueryParams

logger = logging.getLogger(__name__)

API_ENDPOINT = 'https://www.mediafire.com/conversion_server.php'


class ConversionServerError(Exception):
    """Conversion Server Errors"""
    def __init__(self, message, status):
        self.message = message
        self.status = status
        super(ConversionServerError, self).__init__(message, status)

    def __str__(self):
        return "{}: {}".format(self.status, self.message)


class ConversionServerClient(object):
    """Conversion Server client"""

    def __init__(self):
        self.http = requests.Session()

    def request(self, hash_, quickkey, doc_type, page=None,
                output=None, size_id=None, metadata=None,
                request_conversion_only=None):
        """Query conversion server

        hash_: 4 characters of file hash
        quickkey: File quickkey
        doc_type: "i" for image, "d" for documents
        page: The page to convert. If page is set to 'initial', the first
              10 pages of the document will be provided. (document)
        output: "pdf", "img", or "swf" (document)
        size_id: 0,1,2 (document)
                 0-9, a-f, z (image)
        metadata: Set to 1 to get metadata dict
        request_conversion_only: Request conversion w/o content
        """

        if len(hash_) > 4:
            hash_ = hash_[:4]

        query = QueryParams({
            'quickkey': quickkey,
            'doc_type': doc_type,
            'page': page,
            'output': output,
            'size_id': size_id,
            'metadata': metadata,
            'request_conversion_only': request_conversion_only
        })

        url = API_ENDPOINT + '?' + hash_ + '&' + urlencode(query)

        response = self.http.get(url, stream=True)

        if response.status_code == 204:
            raise ConversionServerError("Unable to fulfill request. "
                                        "The document will not be converted.",
                                        response.status_code)

        response.raise_for_status()

        if response.headers['content-type'] == 'application/json':
            return response.json()

        return response
