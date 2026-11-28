"""
Ambil data cuaca historis harian (daily) NASA POWER (MERRA-2)
untuk seluruh sel grid hotspot VIIRS Kalimantan (2021-2025).

- Titik di-snap ke grid 0.5 derajat (sesuai resolusi asli MERRA-2 0.5 x 0.625 deg).
- Rentang tanggal: 2020-12-01 s/d 2025-12-31 (padding 31 hari sebelum 2021-01-01
  untuk fitur lag kekeringan 1-30 hari).
- Output: daily_weather.csv
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

RAW_CSV = Path("nasa_viirs_kalimantan_raw.csv")
OUT_CSV = Path("daily_weather.csv")
GRID_CSV = Path("grid_cells.csv")

GRID_SIZE = 0.5          # derajat (~55 km, sesuai resolusi MERRA-2)
START_DATE = "20201201"  # 31 hari padding sebelum 2021-01-01
END_DATE = "20251231"
MAX_WORKERS = 4

PARAMETERS = "T2M,T2M_MAX,RH2M,PRECTOTCORR,WS10M,WS10M_MAX,GWETTOP"
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def build_grid() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV, usecols=["latitude", "longitude"])
    df["lat_g"] = (df["latitude"] / GRID_SIZE).round() * GRID_SIZE
    df["lon_g"] = (df["longitude"] / GRID_SIZE).round() * GRID_SIZE
    grid = (
        df.groupby(["lat_g", "lon_g"], as_index=False)
        .size()
        .rename(columns={"size": "n_points"})
        .sort_values(["lat_g", "lon_g"])
        .reset_index(drop=True)
    )
    grid.insert(0, "cell_id", grid.index)
    grid.to_csv(GRID_CSV, index=False)
    print(f"Grid: {len(grid)} sel unik dari {len(df):,} titik", flush=True)
    return grid


def fetch_cell(cell_id: int, lat: float, lon: float) -> pd.DataFrame:
    params = {
        "parameters": PARAMETERS,
        "community": "AG",
        "longitude": f"{lon:.2f}",
        "latitude": f"{lat:.2f}",
        "start": START_DATE,
        "end": END_DATE,
        "format": "CSV",
    }
    last_err = None
    for attempt in range(5):
        try:
            r = requests.get(URL, params=params, timeout=60)
            if r.status_code == 200:
                lines = r.text.splitlines()
                header_idx = next(
                    i for i, ln in enumerate(lines) if ln.startswith("YEAR,DOY,")
                )
                df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
                df = df.replace(-999, np.nan)
                df["date"] = pd.to_datetime(
                    df["YEAR"].astype(str) + df["DOY"].astype(str).str.zfill(3),
                    format="%Y%j",
                )
                df["cell_id"] = cell_id
                df["temperature_2m_mean"] = df["T2M"]
                df["temperature_2m_max"] = df["T2M_MAX"]
                df["relative_humidity_2m_mean"] = df["RH2M"]
                df["precipitation_sum"] = df["PRECTOTCORR"]
                df["wind_speed_10m_mean"] = df["WS10M"] * 3.6
                df["wind_speed_10m_max"] = df["WS10M_MAX"] * 3.6
                df["soil_moisture_0_to_7cm_mean"] = df["GWETTOP"]

                # VPD (kPa) via Tetens formula using T2M_MAX & RH2M
                es = 0.6108 * np.exp(
                    (17.27 * df["T2M_MAX"]) / (df["T2M_MAX"] + 237.3)
                )
                df["vapour_pressure_deficit_max"] = es * (1.0 - df["RH2M"] / 100.0)

                cols = [
                    "cell_id",
                    "date",
                    "temperature_2m_mean",
                    "temperature_2m_max",
                    "relative_humidity_2m_mean",
                    "precipitation_sum",
                    "wind_speed_10m_mean",
                    "wind_speed_10m_max",
                    "soil_moisture_0_to_7cm_mean",
                    "vapour_pressure_deficit_max",
                ]
                return df[cols]
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
        time.sleep(2**attempt)
    raise RuntimeError(f"Sel {cell_id} gagal setelah 5 percobaan: {last_err}")


def main() -> None:
    grid = build_grid()
    done_ids: set[int] = set()
    chunks: list[pd.DataFrame] = []

    if OUT_CSV.exists():
        prev = pd.read_csv(OUT_CSV)
        prev["date"] = pd.to_datetime(prev["date"])
        done_ids = set(prev["cell_id"].unique())
        chunks.append(prev)
        print(f"resume: {len(done_ids)}/{len(grid)} sel sudah ada", flush=True)

    todo = grid[~grid["cell_id"].isin(done_ids)]
    total = len(grid)
    done_count = len(done_ids)

    if not todo.empty:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(
                    fetch_cell, int(row.cell_id), float(row.lat_g), float(row.lon_g)
                ): int(row.cell_id)
                for row in todo.itertuples(index=False)
            }
            for fut in as_completed(futures):
                df_cell = fut.result()
                chunks.append(df_cell)
                done_count += 1
                if done_count % 25 == 0 or done_count == total:
                    out = (
                        pd.concat(chunks, ignore_index=True)
                        .drop_duplicates(subset=["cell_id", "date"])
                        .sort_values(["cell_id", "date"])
                        .reset_index(drop=True)
                    )
                    out.to_csv(OUT_CSV, index=False)
                    chunks = [out]
                    print(f"progres: {done_count}/{total} sel tersimpan", flush=True)

    final_df = pd.read_csv(OUT_CSV)
    print(f"Selesai: {OUT_CSV} ({len(final_df):,} baris, {final_df['cell_id'].nunique()} sel)", flush=True)


if __name__ == "__main__":
    main()
