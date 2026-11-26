"""
Ambil data cuaca historis ERA5 via Open-Meteo Archive API
untuk seluruh titik hotspot VIIRS Kalimantan.

- Titik di-snap ke grid 0.1 derajat (resolusi ERA5-Land ~11 km),
  sehingga 35.827 titik hanya butuh ~1.540 sel unik.
- Batching: 50 koordinat per request -> ~31 panggilan API.
- Output: hourly_weather.csv (per sel grid, per jam)
"""

import io
import time
from pathlib import Path

import pandas as pd
import requests

RAW_CSV = Path("nasa_viirs_kalimantan_raw.csv")
OUT_CSV = Path("hourly_weather.csv")
GRID_CSV = Path("grid_cells.csv")

GRID_SIZE = 0.1          # derajat, resolusi ERA5-Land
BATCH_SIZE = 50          # koordinat per request
START_DATE = "2026-10-11"  # 7 hari padding sebelum data FRP pertama
END_DATE = "2026-11-02"    # 1 hari setelah data FRP terakhir

HOURLY_VARS = (
    "temperature_2m,"
    "relative_humidity_2m,"
    "precipitation,"
    "wind_speed_10m,"
    "soil_moisture_0_to_7cm,"
    "vapour_pressure_deficit"
)

URL = "https://archive-api.open-meteo.com/v1/archive"


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
    print(f"Grid: {len(grid)} sel unik dari {len(df)} titik")
    return grid


def fetch_batch(lats: list[str], lons: list[str], session: requests.Session) -> str:
    params = {
        "latitude": ",".join(lats),
        "longitude": ",".join(lons),
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": HOURLY_VARS,
        "format": "csv",
    }
    last_err = None
    for attempt in range(6):
        try:
            r = session.get(URL, params=params, timeout=60)
            if r.status_code == 200:
                return r.text
            last_err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last_err = str(e)
        wait = 60 if "429" in str(last_err) else 2**attempt
        print(f"  retry dalam {wait}s ({last_err})")
        time.sleep(wait)
    raise RuntimeError(f"Gagal setelah 6 percobaan: {last_err}")


def main() -> None:
    grid = build_grid()
    session = requests.Session()

    lat_str = grid["lat_g"].map(lambda v: f"{v:.2f}").tolist()
    lon_str = grid["lon_g"].map(lambda v: f"{v:.2f}").tolist()

    n_batches = (len(grid) + BATCH_SIZE - 1) // BATCH_SIZE
    chunks: list[pd.DataFrame] = []
    first_batch = 1

    # resume: muat hasil batch sebelumnya jika ada
    if OUT_CSV.exists():
        prev = pd.read_csv(OUT_CSV)
        prev["time"] = pd.to_datetime(prev["time"])
        done_ids = set(prev["cell_id"].unique())
        chunks.append(prev)
        first_batch = len(done_ids) // BATCH_SIZE + 1
        print(f"resume: {len(done_ids)} sel sudah ada, lanjut batch {first_batch}")

    for b in range(first_batch, n_batches + 1):
        i = (b - 1) * BATCH_SIZE
        csv_text = fetch_batch(
            lat_str[i : i + BATCH_SIZE], lon_str[i : i + BATCH_SIZE], session
        )
        lines = csv_text.splitlines()
        # CSV multi-lokasi punya 2 bagian: metadata lalu data (header "location_id,time,...")
        data_start = next(
            idx for idx, ln in enumerate(lines) if ln.startswith("location_id,time")
        )
        body = "\n".join(lines[data_start:])
        df = pd.read_csv(io.StringIO(body))
        df["location_id"] = df["location_id"].astype(int)
        # location_id lokal per batch (0..BATCH_SIZE-1) -> geser dengan offset
        df["cell_id"] = df["location_id"] + (b - 1) * BATCH_SIZE
        chunks.append(df)
        print(f"batch {b}/{n_batches} ok ({len(df)} baris)")
        time.sleep(3)  # hindari rate limit per menit

    hourly = pd.concat(chunks, ignore_index=True)
    hourly = hourly.rename(
        columns={
            "temperature_2m (\u00b0C)": "temperature_2m",
            "relative_humidity_2m (%)": "relative_humidity_2m",
            "precipitation (mm)": "precipitation",
            "wind_speed_10m (km/h)": "wind_speed_10m",
            "soil_moisture_0_to_7cm (m\u00b3/m\u00b3)": "soil_moisture_0_to_7cm",
            "vapour_pressure_deficit (kPa)": "vapour_pressure_deficit",
        }
    )
    hourly["time"] = pd.to_datetime(hourly["time"])
    hourly = hourly.sort_values(["cell_id", "time"]).reset_index(drop=True)
    hourly.to_csv(OUT_CSV, index=False)
    print(f"Selesai: {OUT_CSV} ({len(hourly)} baris)")


if __name__ == "__main__":
    main()
