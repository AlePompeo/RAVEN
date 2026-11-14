# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest

from backend.domain.raven.discovery import features as ft


def test_the_polar_candidates_have_physical_finite_features() -> None:
    f = ft.polar_features()
    assert f.x.shape == (len(f.lat), len(ft.NAMES)) and f.size == 384
    assert (
        50_000 < len(f.lat) < 120_000
    )  # most of the 384 x 384 disc (the rim and unreadable cells are not candidates)
    assert np.isfinite(f.x).all() and f.lat.max() <= -75.0 and f.lat.min() >= -90.0
    col = {n: f.x[:, i] for i, n in enumerate(f.names)}
    for pct in ("sun", "earth", "both"):
        assert 0.0 <= col[pct].min() and col[pct].max() <= 100.0 + 1e-6, pct
    assert (
        col["both"] <= np.minimum(col["sun"], col["earth"]) + 1.0
    ).all()  # both bodies at once cannot exceed either alone
    assert col["sun_gap"].min() >= 0.0 and col["earth_gap"].max() > 24.0
    assert 0.0 <= col["rho"].min() and col["rho"].max() <= 1.0


def test_a_missing_layer_is_an_error_not_a_default(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        ft.polar_features(tmp_path)


def test_decode_marks_no_data_as_nan_and_refuses_a_wrong_size() -> None:
    import base64

    ok = {
        "size": 2,
        "data_b64": base64.b64encode(bytes([0, 1, 128, 255])).decode(),
        "min": 10.0,
        "max": 20.0,
        "nodata": 0,
    }
    v = ft.decode(ok)
    assert np.isnan(v[0, 0]) and v[0, 1] == 10.0 and v[1, 1] == 20.0
    with pytest.raises(ValueError):
        ft.decode({**ok, "size": 3})


class _Pts:
    def __init__(self, lat: list[float], lon: list[float]) -> None:
        self.lat_deg, self.lon_deg_east = lat, lon


class _Engine:
    """Sun over longitude 0 and Earth over longitude 180 for the whole window: no cell sees both on a flat Moon."""

    def subsolar_point(self, _body: str, times: list) -> _Pts:  # type: ignore[type-arg]
        return _Pts([0.0] * len(times), [0.0] * len(times))

    def sub_earth_point(self, _body: str, times: list) -> _Pts:  # type: ignore[type-arg]
        return _Pts([0.0] * len(times), [180.0] * len(times))


def test_window_features_replace_the_yearly_ones_with_the_window_values() -> None:
    from datetime import UTC, datetime

    f = ft.polar_features()
    w = ft.window_features(f, _Engine(), datetime(2027, 4, 7, tzinfo=UTC), 14.0)
    assert w.x.shape == f.x.shape and np.isfinite(w.x).all()
    i = {n: k for k, n in enumerate(f.names)}
    # the geometry is fixed (the bodies do not move), so a cell is lit all the window or never: shares are close to 0 or 100
    sun = w.x[:, i["sun"]]
    assert ((sun < 1.0) | (sun > 99.0)).mean() > 0.9
    assert (w.x[:, i["both"]] <= np.minimum(w.x[:, i["sun"]], w.x[:, i["earth"]]) + 1e-9).all()
    # a window of 14 days is not the year: the shares differ from the yearly layer
    assert not np.allclose(sun, f.x[:, i["sun"]])
    # what is not a window quantity is untouched
    for name in ("rho", "sin_lon", "cos_lon", "elevation", "slope"):
        assert np.array_equal(w.x[:, i[name]], f.x[:, i[name]])
    # the longest night cannot exceed the window plus one sampling step (the run is counted in samples)
    assert w.x[:, i["sun_gap"]].max() <= 14 * 24 + 2.0
