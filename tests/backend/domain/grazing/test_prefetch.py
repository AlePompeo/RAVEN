# SPDX-License-Identifier: Apache-2.0
import pytest

from backend.domain.grazing.dem import DemOutOfCoverage, LolaDem
from backend.domain.grazing.prefetch import main, tiles_for_site
from backend.domain.lunar.model import load_sites


def test_tiles_cover_the_radius_and_are_few() -> None:
    dem = LolaDem(allow_download=False)
    s = next(x for x in load_sites() if x.id == "malapert-massif")
    t = tiles_for_site(dem, s.lat_deg, s.lon_deg_east, 10_500.0)
    assert 1 <= len(t) <= 80 and len(set(t)) == len(t)
    row, col = dem.pixel(s.lat_deg, s.lon_deg_east)
    assert (int(row) // 128, int(col) // 128) in t
    assert len(tiles_for_site(dem, s.lat_deg, s.lon_deg_east, 600.0)) <= 4


def test_site_outside_coverage_is_an_error_not_a_guess() -> None:
    dem = LolaDem(allow_download=False)
    a = next(x for x in load_sites() if x.id == "apollo11")
    with pytest.raises(DemOutOfCoverage):
        tiles_for_site(dem, a.lat_deg, a.lon_deg_east, 10_500.0)


def test_dry_run_lists_without_downloading(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert (
        "shackleton:" in out and "apollo11" not in out and "cabeus" not in out
    )  # the default install: the first polar sites
    assert main(["--dry-run", "--all-sites"]) == 0
    out = capsys.readouterr().out
    assert "apollo11: fuori copertura DEM" in out and "cabeus" in out
    with pytest.raises(SystemExit):
        main(["--radius-m", "5"])


def test_parallel_download_reports_progress_and_counts_failures(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import threading
    from types import SimpleNamespace

    from backend.domain.grazing.dem import DemUnavailable
    from backend.domain.grazing.prefetch import _download

    seen: set[int] = set()
    lock = threading.Lock()

    def tile(ti: int, tj: int) -> None:
        if tj == 3:
            raise DemUnavailable("down")
        with lock:
            seen.add(threading.get_ident())

    dem = SimpleNamespace(spec=SimpleNamespace(id="x"), tile=tile)
    todo = [(i, j) for i in range(10) for j in range(5)]
    failed = _download(dem, todo, jobs=8)  # type: ignore[arg-type]
    out = capsys.readouterr().out
    assert failed == 10  # the tiles with tj == 3
    assert "PROGRESS 50 50" in out  # the last line always says it is complete
    assert len(seen) >= 1
    assert _download(dem, [], jobs=8) == 0  # type: ignore[arg-type]
