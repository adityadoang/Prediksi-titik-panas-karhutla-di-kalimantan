"""
Tarik data hotspot historis NASA FIRMS VIIRS (S-NPP) untuk wilayah Kalimantan
selama 5 tahun (2021-2025) dari arsip tahunan resmi NASA FIRMS.

Bounding box Kalimantan (sesuai README.md):
- Latitude : -4.5 s/d 4.5
- Longitude: 108.5 s/d 119.5

Output: nasa_viirs_kalimantan_raw.csv
"""

import io
from pathlib import Path

import pandas as pd
import requests

YEARS = [2021, 2022, 2023, 2024, 2025]
LAT_MIN, LAT_MAX = -4.5, 4.5
LON_MIN, LON_MAX = 108.5, 119.5

OUT_CSV = Path("nasa_viirs_kalimantan_raw.csv")
URL_TMPL = (
    "https://firms.modaps.eosdis.nasa.gov/data/country/"
    "viirs-snpp/{year}/viirs-snpp_{year}_Indonesia.csv"
)


def main() -> None:
    session = requests.Session()
    frames: list[pd.DataFrame] = []

    for year in YEARS:
        url = URL_TMPL.format(year=year)
        print(f"Mengunduh {year}: {url}")
        r = session.get(url, timeout=120)
        r.raise_for_status()

        df = pd.read_csv(io.StringIO(r.text), low_memory=False)
        mask = (
            df["latitude"].between(LAT_MIN, LAT_MAX)
            & df["longitude"].between(LON_MIN, LON_MAX)
        )
        sub = df.loc[mask].copy()
        print(f"  {year}: {len(df):,} baris Indonesia -> {len(sub):,} baris Kalimantan")
        frames.append(sub)

    combined = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["acq_date", "acq_time", "latitude", "longitude"])
        .reset_index(drop=True)
    )
    combined.to_csv(OUT_CSV, index=False)
    print(
        f"\nSelesai: {OUT_CSV} ({len(combined):,} baris, "
        f"{combined['acq_date'].min()} s/d {combined['acq_date'].max()})"
    )


if __name__ == "__main__":
    main()
