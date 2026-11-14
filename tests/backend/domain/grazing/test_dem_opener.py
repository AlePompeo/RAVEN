# SPDX-License-Identifier: Apache-2.0
import io
import urllib.error
import urllib.request

import pytest

from backend.domain.grazing.dem import _opener


def test_an_http_error_status_raises_instead_of_returning_none() -> None:
    """A throttling server (429/503) must be a retryable error: the opener used to return None and the caller crashed."""
    req = urllib.request.Request("https://example.invalid/x")
    for code in (429, 503):
        with pytest.raises(urllib.error.HTTPError) as err:
            _opener().error("http", req, io.BytesIO(b""), code, "busy", {})  # type: ignore[arg-type]
        assert err.value.code == code
