"""Access MeteoSwiss SwissMetNet observations from the Open Government Data portal.

Data are served via the swisstopo STAC API (collection ``ch.meteoschweiz.ogd-smn``):
https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-smn

Each station is a STAC item with one CSV per granularity and period, e.g.
``ogd-smn_alt_t_recent.csv``:

granularity  t = 10 min, h = hourly, d = daily, m = monthly, y = yearly
period       now        = today since 00 UTC (updated every 10 min)
             recent     = 1 January of the current year until yesterday
             historical = start of measurements until 31 Dec last year
                          (t and h split into decades, e.g. ``historical_2010-2019``)

Timestamps (``reference_timestamp``) are in UTC.

Foehn index parameters:
    wcc006s0  foehn index, 10 min code: 0 = no foehn, 1 = foehn mixing air, 2 = foehn
    wcc006h0  minutes of foehn per hour
    wcc006d0  minutes of foehn per day
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

STAC_API = "https://data.geo.admin.ch/api/stac/v1"
COLLECTION = "ch.meteoschweiz.ogd-smn"
DATA_URL = f"https://data.geo.admin.ch/{COLLECTION}"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

# Files that keep changing are re-downloaded once they are older than this (s).
TTL = {"now": 10 * 60, "recent": 12 * 3600, "historical": 30 * 86400, "static": 86400}

FOEHN_PARAMS = {"t": "wcc006s0", "h": "wcc006h0", "d": "wcc006d0"}
FOEHN_CODES = {0: "no foehn", 1: "foehn mixing air", 2: "foehn"}

_session = requests.Session()
_session.headers["User-Agent"] = "foehn-explorer/0.1 (python-requests)"


# --------------------------------------------------------------------------- download
def _download(url: str, kind: str) -> Path:
    """Download ``url`` into the cache unless a fresh enough copy exists."""
    path = CACHE_DIR / COLLECTION / url.rsplit(f"{COLLECTION}/", 1)[-1]
    if path.exists() and time.time() - path.stat().st_mtime < TTL[kind]:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    r = _session.get(url, timeout=120)
    r.raise_for_status()
    tmp = path.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.replace(path)
    return path


def _read_csv(path: Path) -> pd.DataFrame:
    # Data files are UTF-8, some metadata files are Latin-1.
    try:
        return pd.read_csv(path, sep=";", encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(path, sep=";", encoding="latin-1")


# --------------------------------------------------------------------------- metadata
def load_meta(name: str) -> pd.DataFrame:
    """Load collection metadata: ``"parameters"``, ``"stations"`` or ``"datainventory"``."""
    url = f"{DATA_URL}/ogd-smn_meta_{name}.csv"
    return _read_csv(_download(url, "static"))


def search_parameters(text: str | None = None, granularity: str | None = None) -> pd.DataFrame:
    """Search parameters by (regex) text in short name, descriptions or group."""
    p = load_meta("parameters")
    if text:
        cols = [c for c in p.columns if c.startswith(("parameter_description", "parameter_group"))]
        cols.append("parameter_shortname")
        hay = p[cols].astype(str).agg(" | ".join, axis=1)
        p = p[hay.str.contains(text, case=False, regex=True)]
    if granularity:
        p = p[p["parameter_granularity"].str.upper() == granularity.upper()]
    keep = ["parameter_shortname", "parameter_description_en", "parameter_description_de",
            "parameter_granularity", "parameter_unit"]
    return p[keep].reset_index(drop=True)


def stations_with(parameter: str) -> pd.DataFrame:
    """Stations that measure ``parameter``, with location and data availability."""
    inv = load_meta("datainventory")
    inv = inv[inv["parameter_shortname"] == parameter]
    st = load_meta("stations")
    cols = ["station_abbr", "station_name", "station_canton", "station_height_masl",
            "station_coordinates_wgs84_lat", "station_coordinates_wgs84_lon"]
    out = inv[["station_abbr", "data_since", "data_till"]].merge(st[cols], on="station_abbr")
    out["data_since"] = pd.to_datetime(out["data_since"], format="%d.%m.%Y %H:%M")
    return out.rename(columns={"station_coordinates_wgs84_lat": "lat",
                               "station_coordinates_wgs84_lon": "lon",
                               "station_height_masl": "height_masl"}
                      ).sort_values("station_abbr").reset_index(drop=True)


def foehn_stations() -> pd.DataFrame:
    """All SwissMetNet stations that provide the foehn index."""
    return stations_with(FOEHN_PARAMS["t"])


# --------------------------------------------------------------------------- data files
def _utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")


_ASSET_RE = re.compile(r"ogd-smn_(?P<stn>[a-z0-9]+)_(?P<gran>[tdhmy])"
                       r"(?:_(?P<period>now|recent|historical)(?:_(?P<y0>\d{4})-(?P<y1>\d{4}))?)?\.csv$")


def station_files(station: str) -> pd.DataFrame:
    """List the CSV assets of a station (from the STAC item) with their time coverage."""
    url = f"{STAC_API}/collections/{COLLECTION}/items/{station.lower()}"
    r = _session.get(url, timeout=60)
    r.raise_for_status()
    now = datetime.now(timezone.utc)
    this_year = pd.Timestamp(now.year, 1, 1, tz="UTC")
    today = pd.Timestamp(now.date(), tz="UTC")
    rows = []
    for name, asset in r.json()["assets"].items():
        m = _ASSET_RE.match(name)
        if not m:
            continue
        period = m["period"] or "static"  # monthly/yearly files have no period
        if period == "now":
            start, end = today, today + pd.Timedelta(days=1)
        elif period == "recent":
            start, end = this_year, today
        elif m["y0"]:
            start = pd.Timestamp(int(m["y0"]), 1, 1, tz="UTC")
            end = min(pd.Timestamp(int(m["y1"]) + 1, 1, 1, tz="UTC"), this_year)
        elif period == "historical":
            start, end = pd.Timestamp(1800, 1, 1, tz="UTC"), this_year
        else:
            start, end = pd.Timestamp(1800, 1, 1, tz="UTC"), today + pd.Timedelta(days=1)
        rows.append(dict(name=name, granularity=m["gran"], period=period,
                         start=start, end=end, href=asset["href"]))
    return pd.DataFrame(rows).sort_values(["granularity", "start"]).reset_index(drop=True)


def load_station(station: str, granularity: str = "h", start=None, end=None,
                 parameters: list[str] | None = None) -> pd.DataFrame:
    """Load observations of one station for a time range.

    Picks the needed now/recent/historical files automatically, caches them under
    ``data/cache`` and returns a DataFrame indexed by UTC time.
    """
    start = _utc(start) if start is not None else pd.Timestamp(1800, 1, 1, tz="UTC")
    end = _utc(end) if end is not None else pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1)
    files = station_files(station)
    files = files[(files["granularity"] == granularity)
                  & (files["start"] < end) & (files["end"] > start)]
    if files.empty:
        raise ValueError(f"No '{granularity}' files for {station} between {start} and {end}")

    frames = []
    for f in files.itertuples():
        df = _read_csv(_download(f.href, f.period))
        if parameters:
            df = df[["station_abbr", "reference_timestamp"]
                    + [p for p in parameters if p in df.columns]]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df.pop("reference_timestamp"), format="%d.%m.%Y %H:%M", utc=True)
    df = df.drop_duplicates("time", keep="last").set_index("time").sort_index()
    return df.loc[start:end - pd.Timedelta(seconds=1)]


def load_foehn(stations: str | list[str], granularity: str = "h", start=None, end=None,
               extra: list[str] | None = None) -> pd.DataFrame:
    """Foehn index for one or several stations in long format.

    ``granularity="t"`` gives the 10-min code (0/1/2), ``"h"``/``"d"`` foehn minutes.
    ``extra`` adds further parameters, e.g. wind speed ``fkl010h0`` or temperature ``tre200h0``.
    """
    if isinstance(stations, str):
        stations = [stations]
    params = [FOEHN_PARAMS[granularity]] + list(extra or [])
    frames = [load_station(s, granularity, start, end, params) for s in stations]
    out = pd.concat(frames).rename(columns={FOEHN_PARAMS[granularity]: "foehn"})
    return out.reset_index().set_index(["station_abbr", "time"]).sort_index()
