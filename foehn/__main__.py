"""Command line access to MeteoSwiss OGD observations.

    python -m foehn params foehn            # search parameters
    python -m foehn stations                # stations with foehn index
    python -m foehn files ALT               # data files of a station
    python -m foehn fetch ALT CHU -g h --start 2025-01-01 --end 2025-04-01 -o foehn.csv
"""

import argparse

import pandas as pd

from . import obs


def main() -> None:
    ap = argparse.ArgumentParser(prog="foehn", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("params", help="search parameters by text (regex)")
    p.add_argument("text", nargs="?")
    p.add_argument("-g", "--granularity", choices=list("tdhmy"))

    p = sub.add_parser("stations", help="stations providing a parameter (default: foehn index)")
    p.add_argument("-p", "--parameter", default=obs.FOEHN_PARAMS["t"])

    p = sub.add_parser("files", help="list data files of a station")
    p.add_argument("station")

    p = sub.add_parser("fetch", help="download foehn index for stations")
    p.add_argument("stations", nargs="+")
    p.add_argument("-g", "--granularity", choices=["t", "h", "d"], default="h")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--extra", nargs="*", default=[], help="additional parameter short names")
    p.add_argument("-o", "--output", help="write CSV instead of printing a summary")

    a = ap.parse_args()
    pd.set_option("display.width", 200, "display.max_rows", 200, "display.max_colwidth", 60)

    if a.cmd == "params":
        print(obs.search_parameters(a.text, a.granularity).to_string(index=False))
    elif a.cmd == "stations":
        print(obs.stations_with(a.parameter).to_string(index=False))
    elif a.cmd == "files":
        print(obs.station_files(a.station).drop(columns="href").to_string(index=False))
    elif a.cmd == "fetch":
        df = obs.load_foehn(a.stations, a.granularity, a.start, a.end, a.extra)
        if a.output:
            df.to_csv(a.output)
            print(f"wrote {len(df)} rows to {a.output}")
        else:
            print(df.tail(10))
            if a.granularity == "t":
                summary = df["foehn"].groupby(level=0).value_counts().unstack(fill_value=0)
                print("\n10-min intervals per foehn code:\n", summary)
            else:
                hours = df["foehn"].groupby(level=0).sum() / 60
                print("\nTotal foehn hours:\n", hours.round(1))


if __name__ == "__main__":
    main()
