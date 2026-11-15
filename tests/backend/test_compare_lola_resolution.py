# SPDX-License-Identifier: Apache-2.0
"""HTTP range checks for the optional LOLA sensitivity experiment."""

import io
from unittest.mock import patch

import pytest

from scripts.compare_lola_resolution import Remote

PRODUCT = ("data.tif", 10, 'W/"revision"')


class Response(io.BytesIO):
    def __init__(self, data: bytes, status: int, etag: str, content_range: str) -> None:
        super().__init__(data)
        self.status = status
        self.headers = {"ETag": etag, "Content-Range": content_range}


def test_remote_accepts_exact_range_and_advances_position() -> None:
    response = Response(b"345", 206, PRODUCT[2], "bytes 3-5/10")
    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        source = Remote(PRODUCT)
        source.seek(3)
        assert source.read(3) == b"345"
        assert source.tell() == 6
        assert urlopen.call_args.args[0].get_header("Range") == "bytes=3-5"


@pytest.mark.parametrize(
    ("data", "status", "etag", "content_range"),
    [
        (b"345", 200, PRODUCT[2], "bytes 3-5/10"),
        (b"345", 206, 'W/"changed"', "bytes 3-5/10"),
        (b"345", 206, PRODUCT[2], "bytes 2-4/10"),
        (b"34", 206, PRODUCT[2], "bytes 3-5/10"),
    ],
)
def test_remote_rejects_mismatched_response(
    data: bytes, status: int, etag: str, content_range: str
) -> None:
    with patch("urllib.request.urlopen", return_value=Response(data, status, etag, content_range)):
        source = Remote(PRODUCT)
        source.seek(3)
        with pytest.raises(ValueError):
            source.read(3)
        assert source.tell() == 3
