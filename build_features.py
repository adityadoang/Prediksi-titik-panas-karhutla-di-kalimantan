"""
Gabungkan data cuaca harian NASA POWER (MERRA-2) (2020-12-01 s/d 2025-12-31) dengan
titik panas VIIRS Kalimantan multi-tahun (2021-2025).

- Fitur musiman: month, doy_sin, doy_cos (menangkap siklus kemarau/hujan).
- Fitur lag 1, 3, 7, 14, 30 hari: akumulasi hujan, rata-rata RH/suhu/angin,
  min kelembapan tanah, maks VPD (kekeringan bersifat akumulatif).
- Join ke data FRP berdasarkan tanggal + sel grid 0.5 derajat.
- Kolom `type` FIRMS ikut disimpan (0 = kebakaran vegetasi, 2 = sumber panas statis,
  3 = lepas pantai) agar notebook bisa memakai hanya kebakaran vegetasi.

Output: data_karhutla_dengan_cuaca.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

GRID_SIZE = 0.5
LAG_WINDOWS = (1, 3, 7, 14, 30)

DAILY_CSV = Path("daily_weather.csv")
RAW_CSV = Path("nasa_viirs_kalimantan_raw.csv")
GRID_CSV = Path("grid_cells.csv")
OUT_CSV = Path("data_karhutla_dengan_cuaca.csv")


def build_lag_features(daily: pd.DataFrame) -> pd.DataFrame:
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values(["cell_id", "date"]).reset_index(drop=True)
    g = daily.groupby("cell_id", group_keys=False)

    for lag in LAG_WINDOWS:
        daily[f"precip_acc_{lag}d"] = g["precipitation_sum"].transform(
            lambda s: s.shift(1).rolling(lag, min_periods=1).sum()
        )
        daily[f"rh_mean_{lag}d"] = g["relative_humidity_2m_mean"].transform(
            lambda s: s.shift(1).rolling(lag, min_periods=1).mean()
        )
        daily[f"temp_mean_{lag}d"] = g["temperature_2m_mean"].transform(
            lambda s: s.shift(1).rolling(lag, min_periods=1).mean()
        )
        daily[f"wind_mean_{lag}d"] = g["wind_speed_10m_mean"].transform(
            lambda s: s.shift(1).rolling(lag, min_periods=1).mean()
        )
        daily[f"soil_min_{lag}d"] = g["soil_moisture_0_to_7cm_mean"].transform(
            lambda s: s.shift(1).rolling(lag, min_periods=1).min()
        )
        daily[f"vpd_max_{lag}d"] = g["vapour_pressure_deficit_max"].transform(
            lambda s: s.shift(1).rolling(lag, min_periods=1).max()
        )

    # Fitur musiman untuk pola kemarau/hujan tahunan
    doy = daily["date"].dt.dayofyear
    daily["month"] = daily["date"].dt.month
    daily["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    daily["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    return daily


def main() -> None:
    daily = pd.read_csv(DAILY_CSV)
    n_cell = daily["cell_id"].nunique()
    counts = daily.groupby("cell_id").size()
    assert counts.min() == counts.max(), "ada sel dengan jumlah hari berbeda"
    print(f"daily: {len(daily):,} baris, {n_cell} sel, {counts.iloc[0]} hari/sel")
    print("missing per kolom:")
    print(daily.isna().sum().to_string())

    daily = build_lag_features(daily)

    grid = pd.read_csv(GRID_CSV)
    frp = pd.read_csv(
        RAW_CSV,
        usecols=[
            "latitude",
            "longitude",
            "acq_date",
            "acq_time",
            "frp",
            "bright_ti4",
            "bright_ti5",
            "scan",
            "track",
            "confidence",
            "daynight",
            "type",
        ],
    )
    frp["date"] = pd.to_datetime(frp["acq_date"])

    def to_idx(series: pd.Series) -> pd.Series:
        return (series / GRID_SIZE).round().astype("int64")

    frp["lat_idx"] = to_idx(frp["latitude"])
    frp["lon_idx"] = to_idx(frp["longitude"])
    grid["lat_idx"] = to_idx(grid["lat_g"])
    grid["lon_idx"] = to_idx(grid["lon_g"])

    daily = daily.merge(
        grid[["cell_id", "lat_idx", "lon_idx"]], on="cell_id", how="left"
    )

    merged = frp.merge(
        daily,
        on=["date", "lat_idx", "lon_idx"],
        how="left",
    )

    n_missing = merged["temperature_2m_mean"].isna().sum()
    print(f"\njoin: {len(merged):,} baris, tanpa cuaca: {n_missing}")
    assert n_missing == 0, "ada baris FRP tanpa data cuaca"

    merged = merged.drop(columns=["lat_idx", "lon_idx"])
    merged.to_csv(OUT_CSV, index=False)
    print(f"Selesai: {OUT_CSV} ({len(merged):,} baris, {len(merged.columns)} kolom)")

    print("\ncontoh korelasi fitur cuaca vs FRP:")
    ignore = {
        "latitude",
        "longitude",
        "acq_date",
        "acq_time",
        "frp",
        "bright_ti4",
        "bright_ti5",
        "scan",
        "track",
        "confidence",
        "daynight",
        "type",
        "date",
    }
    weather_cols = [c for c in merged.columns if c not in ignore]
    corr = merged[weather_cols + ["frp"]].corr(numeric_only=True)["frp"]
    print(corr.drop("frp").sort_values(key=abs, ascending=False).head(15).to_string())


if __name__ == "__main__":
    main()
