# SPDX-License-Identifier: Apache-2.0
"""HTTP range checks for the optional LOLA sensitivity experiment."""

import io
from unittest.mock import patch

import numpy as np
import pytest

from scripts.compare_lola_resolution import Remote, main

PRODUCT = ("data.tif", 10, 'W/"revision"')


@pytest.mark.parametrize("latitude", ["-86", "nan", "-91"])
def test_rejects_latitudes_outside_polar_mosaic(latitude: str) -> None:
    with (
        patch("sys.argv", ["compare_lola_resolution", f"--lat={latitude}"]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 2


@pytest.mark.parametrize("missing_sample", [False, True])
def test_missing_window_tiles_only_invalidate_missing_samples(
    missing_sample: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    class Grid:
        tiles_missing = 12

        def __init__(self, *args: object) -> None:
            pass

        def sample(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
            result = np.zeros_like(lat)
            if missing_sample:
                result[1] = np.nan
            return result

    def samples(*args: object) -> tuple[np.ndarray, str]:
        return np.zeros((4, 2001)), "test-hash"

    with (
        patch("sys.argv", ["compare_lola_resolution"]),
        patch("scripts.compare_lola_resolution._Grid", Grid),
        patch("scripts.compare_lola_resolution.LolaDem"),
        patch("scripts.compare_lola_resolution.load_lock"),
        patch("scripts.compare_lola_resolution.samples", samples),
    ):
        if missing_sample:
            with pytest.raises(ValueError, match="non-finite PDS terrain samples"):
                main()
        else:
            main()
            assert "missing window tiles (20 m, 240 m): 12 12" in capsys.readouterr().out


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
