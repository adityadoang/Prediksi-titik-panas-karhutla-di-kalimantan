"""
Gabungkan data cuaca ERA5 (hourly) dengan titik panas VIIRS.

- Agregasi hourly -> harian per sel grid.
- Fitur lag 1-7 hari: akumulasi hujan, rata-rata RH/suhu/angin/VPD,
  min kelembapan tanah (kekeringan bersifat akumulatif).
- Join ke data FRP berdasarkan tanggal + sel grid 0.1 derajat.

Output: data_karhutla_dengan_cuaca.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

GRID_SIZE = 0.1
HOURS_PER_DAY = 24

HOURLY_CSV = Path("hourly_weather.csv")
RAW_CSV = Path("nasa_viirs_kalimantan_raw.csv")
OUT_CSV = Path("data_karhutla_dengan_cuaca.csv")


def build_daily(hourly: pd.DataFrame) -> pd.DataFrame:
    daily = (
        hourly.groupby(["cell_id", hourly["time"].dt.date], as_index=False)
        .agg(
            temperature_2m=("temperature_2m", "mean"),
            relative_humidity_2m=("relative_humidity_2m", "mean"),
            precipitation=("precipitation", "sum"),
            wind_speed_10m=("wind_speed_10m", "mean"),
            soil_moisture_0_to_7cm=("soil_moisture_0_to_7cm", "mean"),
            vapour_pressure_deficit=("vapour_pressure_deficit", "mean"),
            rh_min=("relative_humidity_2m", "min"),
            vpd_max=("vapour_pressure_deficit", "max"),
        )
        .rename(columns={"time": "date"})
    )
    daily["date"] = pd.to_datetime(daily["date"])

    daily = daily.sort_values(["cell_id", "date"])
    g = daily.groupby("cell_id")

    # lag 1-7 hari
    for lag in range(1, 8):
        daily[f"precip_acc_{lag}d"] = g["precipitation"].shift(1).rolling(lag, min_periods=1).sum().reset_index(level=0, drop=True) if False else g["precipitation"].transform(lambda s: s.shift(1).rolling(lag, min_periods=1).sum())
        daily[f"rh_mean_{lag}d"] = g["relative_humidity_2m"].transform(lambda s: s.shift(1).rolling(lag, min_periods=1).mean())
        daily[f"temp_mean_{lag}d"] = g["temperature_2m"].transform(lambda s: s.shift(1).rolling(lag, min_periods=1).mean())
        daily[f"wind_mean_{lag}d"] = g["wind_speed_10m"].transform(lambda s: s.shift(1).rolling(lag, min_periods=1).mean())
        daily[f"soil_min_{lag}d"] = g["soil_moisture_0_to_7cm"].transform(lambda s: s.shift(1).rolling(lag, min_periods=1).min())
        daily[f"vpd_mean_{lag}d"] = g["vapour_pressure_deficit"].transform(lambda s: s.shift(1).rolling(lag, min_periods=1).mean())

    return daily


def main() -> None:
    hourly = pd.read_csv(HOURLY_CSV, parse_dates=["time"])
    n_cell = hourly["cell_id"].nunique()
    # verifikasi kelengkapan hourly (24 jam x n_hari per sel)
    counts = hourly.groupby("cell_id").size()
    assert counts.min() == counts.max(), "ada sel dengan jumlah jam berbeda"
    print(f"hourly: {len(hourly)} baris, {n_cell} sel, {counts.iloc[0]} jam/sel")
    print("missing per kolom:")
    print(hourly.isna().sum().to_string())

    daily = build_daily(hourly)

    grid = pd.read_csv("grid_cells.csv")
    frp = pd.read_csv(
        RAW_CSV,
        usecols=["latitude", "longitude", "acq_date", "acq_time", "frp",
                 "bright_ti4", "confidence"],
    )
    frp["date"] = pd.to_datetime(frp["acq_date"])

    # kunci grid berbasis integer -> aman dari deviasi floating point
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
        left_on=["date", "lat_idx", "lon_idx"],
        right_on=["date", "lat_idx", "lon_idx"],
        how="left",
    )

    n_missing = merged["temperature_2m"].isna().sum()
    print(f"\njoin: {len(merged)} baris, tanpa cuaca: {n_missing}")
    assert n_missing == 0, "ada baris FRP tanpa data cuaca"

    merged = merged.drop(columns=["lat_idx", "lon_idx"])
    merged.to_csv(OUT_CSV, index=False)
    print(f"Selesai: {OUT_CSV} ({len(merged.columns)} kolom)")

    print("\ncontoh korelasi fitur cuaca vs FRP:")
    weather_cols = [c for c in merged.columns if c not in
                    {"latitude", "longitude", "acq_date", "acq_time", "frp",
                     "bright_ti4", "confidence", "date"}]
    corr = merged[weather_cols + ["frp"]].corr(numeric_only=True)["frp"]
    print(corr.drop("frp").sort_values(key=abs, ascending=False).head(15).to_string())


if __name__ == "__main__":
    main()
