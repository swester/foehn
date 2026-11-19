# Foehn explorer

Tools to study foehn in Switzerland with MeteoSwiss Open Government Data (OGD).
Step 1: SwissMetNet observations incl. the MeteoSwiss foehn index. (NWP forecasts follow.)

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Data source

- STAC API: `https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-smn`
- One STAC item per station, CSV files per granularity (`t` 10 min, `h`, `d`, `m`, `y`)
  and period (`now` = today, `recent` = this year until yesterday, `historical` = earlier, decade files for t/h).
- Timestamps are UTC. License CC BY (source: MeteoSwiss).
- Downloads are cached in `data/cache/` (`now` refreshed after 10 min, `recent` after 12 h).

## Foehn index

| parameter  | granularity | meaning |
|------------|-------------|---------|
| `wcc006s0` | 10 min      | code: 0 = no foehn, 1 = foehn mixing air, 2 = foehn |
| `wcc006h0` | hourly      | minutes of foehn in the hour |
| `wcc006d0` | daily       | minutes of foehn in the day |

Available at 39 stations (e.g. ALT Altdorf, CHU Chur, VAD Vaduz, GLA Glarus, LUG Lugano, MAG Magadino), mostly since 2004.

## Usage

```bash
.venv/bin/python -m foehn params foehn          # search parameter catalogue
.venv/bin/python -m foehn stations              # stations with foehn index
.venv/bin/python -m foehn current               # latest foehn index + wind/T/RH at all stations
.venv/bin/python -m foehn current --map output/foehn_current.png   # plus a map
.venv/bin/python -m foehn files ALT             # data files of a station
.venv/bin/python -m foehn fetch ALT CHU -g h --start 2025-01-01 --extra fkl010h0 tre200h0 -o foehn.csv
```

```python
from foehn import obs
obs.search_parameters("wind", granularity="h")
stations = obs.foehn_stations()
df = obs.load_foehn(["ALT", "CHU"], "t", "2025-03-01", "2025-03-10", extra=["fkl010z0", "dkl010z0"])
raw = obs.load_station("ALT", "h", "2024-01-01", "2025-01-01")   # all parameters
```
