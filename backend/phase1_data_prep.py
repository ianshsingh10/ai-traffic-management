"""
Phase 1 — Data Preparation
Flipkart Gridlock 2.0 | Parking Intelligence System
Run: python3 phase1_data_prep.py
Outputs: df_clean.csv, df_scored.csv, summary.json
"""

import pandas as pd
import numpy as np
import json
import ast
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────────────────────────
INPUT_FILE = r"./data/jan to may police violation_anonymized791b166.csv"
OUT_DIR     = Path("./data")
OUT_DIR.mkdir(exist_ok=True)

# Vehicle congestion weight — how much each vehicle type blocks a lane
VEHICLE_WEIGHTS = {
    "MOPED":                0.8,
    "SCOOTER":              1.0,
    "MOTOR CYCLE":          1.0,
    "PASSENGER AUTO":       1.2,
    "GOODS AUTO":           1.2,
    "CAR":                  1.5,
    "JEEP":                 1.5,
    "VAN":                  1.5,
    "OTHERS":               1.5,
    "MAXI-CAB":             2.0,
    "TEMPO":                2.0,
    "MINI LORRY":           2.0,
    "LGV":                  2.0,
    "TOURIST BUS":          2.5,
    "PRIVATE BUS":          2.5,
    "BUS (BMTC/KSRTC)":     2.5,
    "FACTORY BUS":          2.5,
    "SCHOOL VEHICLE":       2.5,
    "HGV":                  3.0,
    "LORRY/GOODS VEHICLE":  3.0,
    "TANKER":               3.0,
    "TRACTOR":              3.0,
}

# Peak hour multiplier — rush hours matter more for congestion
def peak_hour_weight(hour):
    if   7 <= hour <= 10:  return 2.2   # morning rush
    elif 17 <= hour <= 20: return 2.0   # evening rush
    elif 11 <= hour <= 16: return 1.4   # midday
    elif 20 <= hour <= 22: return 1.2   # late evening
    else:                  return 0.8   # off-peak / night

# ── STEP 1: LOAD ─────────────────────────────────────────────────────────────
print("=" * 55)
print("  PHASE 1 — DATA PREPARATION")
print("=" * 55)

print("\n[1/6] Loading raw dataset...")
df = pd.read_csv(INPUT_FILE)
print(f"      Loaded {len(df):,} rows × {len(df.columns)} columns")

# ── STEP 2: FILTER TO APPROVED ONLY ──────────────────────────────────────────
print("\n[2/6] Filtering to approved violations...")
df = df[df["validation_status"] == "approved"].copy()
print(f"      Retained {len(df):,} approved rows")
print(f"      Dropped  {298450 - len(df):,} rows (rejected / pending / duplicate)")

# ── STEP 3: PARSE VIOLATION TYPES ────────────────────────────────────────────
print("\n[3/6] Parsing violation_type JSON strings...")

def parse_violations(v):
    try:
        return ast.literal_eval(v)
    except Exception:
        return []

df["violation_list"]  = df["violation_type"].apply(parse_violations)
df["violation_count"] = df["violation_list"].apply(len)

# Primary violation (first in list)
df["primary_violation"] = df["violation_list"].apply(
    lambda x: x[0] if len(x) > 0 else "UNKNOWN"
)

# One-hot encode the most common violation categories
TOP_VIOLATIONS = [
    "NO PARKING",
    "WRONG PARKING",
    "PARKING IN A MAIN ROAD",
    "PARKING NEAR ROAD CROSSING",
    "PARKING ON FOOTPATH",
    "PARKING NEAR JUNCTION",
    "PARKING IN BUS STOP",
]
for vtype in TOP_VIOLATIONS:
    col = "v_" + vtype.lower().replace(" ", "_")
    df[col] = df["violation_list"].apply(lambda x: 1 if vtype in x else 0)

print(f"      Parsed. Unique primary violations:")
vc = df["primary_violation"].value_counts()
for k, v in vc.head(8).items():
    print(f"        {k:<38} {v:>6,}")

# ── STEP 4: DATETIME FEATURES ────────────────────────────────────────────────
print("\n[4/6] Extracting datetime features...")

df["created_datetime"] = pd.to_datetime(df["created_datetime"], utc=True)
df["created_datetime"] = df["created_datetime"].dt.tz_convert("Asia/Kolkata")  # convert UTC → IST
df["hour"]        = df["created_datetime"].dt.hour
df["day_of_week"] = df["created_datetime"].dt.dayofweek   # 0=Mon, 6=Sun
df["day_name"]    = df["created_datetime"].dt.day_name()
df["month"]       = df["created_datetime"].dt.month
df["month_name"]  = df["created_datetime"].dt.strftime("%B")
df["date"]        = df["created_datetime"].dt.date
df["is_weekend"]  = df["day_of_week"].isin([5, 6]).astype(int)

# Time-of-day bucket
def time_bucket(hour):
    if   6  <= hour < 10:  return "morning_rush"
    elif 10 <= hour < 17:  return "midday"
    elif 17 <= hour < 21:  return "evening_rush"
    elif 21 <= hour < 24:  return "night"
    else:                  return "late_night"

df["time_bucket"] = df["hour"].apply(time_bucket)

print(f"      Date range: {df['created_datetime'].min().date()} → {df['created_datetime'].max().date()}")
print(f"      Hour distribution (top 5):")
top_hours = df["hour"].value_counts().head(5)
for h, c in top_hours.items():
    print(f"        {h:02d}:00  →  {c:,} violations")

# ── STEP 5: CONGESTION IMPACT SCORING ────────────────────────────────────────
print("\n[5/6] Computing congestion impact scores...")

# Vehicle weight
df["vehicle_weight"] = df["vehicle_type"].map(VEHICLE_WEIGHTS).fillna(1.5)

# Peak hour weight
df["peak_weight"] = df["hour"].apply(peak_hour_weight)

# Raw impact score per violation
# Formula: vehicle_weight × peak_weight × violation_count (multi-violation = worse)
df["impact_score"] = (
    df["vehicle_weight"] *
    df["peak_weight"] *
    df["violation_count"].clip(upper=3)   # cap at 3 to avoid outlier blowup
)

# Normalize to 0–100
min_s, max_s = df["impact_score"].min(), df["impact_score"].max()
df["impact_score_norm"] = (
    (df["impact_score"] - min_s) / (max_s - min_s) * 100
).round(2)

print(f"      Score range: {df['impact_score'].min():.2f} – {df['impact_score'].max():.2f}")
print(f"      Mean impact score: {df['impact_score'].mean():.2f}")

# Zone-level aggregation by police_station
print("\n      Zone-level summary (top 10 stations by total impact):")
zone_stats = (
    df.groupby("police_station")
    .agg(
        total_violations=("id", "count"),
        total_impact=("impact_score", "sum"),
        avg_impact=("impact_score", "mean"),
        peak_hour=("hour", lambda x: x.value_counts().idxmax()),
        top_vehicle=("vehicle_type", lambda x: x.value_counts().idxmax()),
        top_violation=("primary_violation", lambda x: x.value_counts().idxmax()),
        avg_lat=("latitude", "mean"),
        avg_lng=("longitude", "mean"),
    )
    .reset_index()
    .sort_values("total_impact", ascending=False)
)

# Normalize zone score 0–100
z_min, z_max = zone_stats["total_impact"].min(), zone_stats["total_impact"].max()
zone_stats["zone_score"] = (
    (zone_stats["total_impact"] - z_min) / (z_max - z_min) * 100
).round(1)

# Priority label
def priority_label(score):
    if score >= 70: return "CRITICAL"
    elif score >= 40: return "HIGH"
    elif score >= 20: return "MEDIUM"
    else: return "LOW"

zone_stats["priority"] = zone_stats["zone_score"].apply(priority_label)

for _, row in zone_stats.head(10).iterrows():
    print(f"        [{row['priority']:<8}] {row['police_station']:<22} "
          f"score={row['zone_score']:5.1f}  violations={row['total_violations']:,}")

# ── STEP 6: SAVE OUTPUTS ─────────────────────────────────────────────────────
print("\n[6/6] Saving outputs...")

# Main cleaned + scored dataset
df_out = df[[
    "id", "latitude", "longitude", "police_station",
    "vehicle_type", "vehicle_weight",
    "primary_violation", "violation_count",
    "created_datetime", "hour", "day_of_week", "day_name",
    "month", "month_name", "date", "is_weekend", "time_bucket",
    "peak_weight", "impact_score", "impact_score_norm",
    "v_no_parking", "v_wrong_parking", "v_parking_in_a_main_road",
    "v_parking_near_road_crossing", "v_parking_on_footpath",
    "v_parking_near_junction", "v_parking_in_bus_stop",
]].copy()

df_out.to_csv(OUT_DIR / "df_clean.csv", index=False)
print(f"      Saved: data/df_clean.csv  ({len(df_out):,} rows)")

zone_stats.to_csv(OUT_DIR / "df_zones.csv", index=False)
print(f"      Saved: data/df_zones.csv  ({len(zone_stats)} zones)")

# Summary JSON for dashboard
summary = {
    "total_violations": int(len(df_out)),
    "date_range": {
        "start": str(df_out["date"].min()),
        "end":   str(df_out["date"].max()),
    },
    "top_zones": zone_stats.head(10)[[
        "police_station", "zone_score", "priority",
        "total_violations", "peak_hour",
        "top_vehicle", "top_violation",
        "avg_lat", "avg_lng"
    ]].to_dict(orient="records"),
    "hourly_distribution": df_out.groupby("hour")["id"].count().to_dict(),
    "vehicle_breakdown": df_out["vehicle_type"].value_counts().head(10).to_dict(),
    "violation_breakdown": df_out["primary_violation"].value_counts().head(8).to_dict(),
    "monthly_trend": df_out.groupby("month_name")["id"].count().to_dict(),
    "time_bucket_dist": df_out["time_bucket"].value_counts().to_dict(),
    "peak_stats": {
        "worst_station":       zone_stats.iloc[0]["police_station"],
        "worst_station_count": int(zone_stats.iloc[0]["total_violations"]),
        "worst_hour":          int(df_out["hour"].value_counts().idxmax()),
        "worst_vehicle":       df_out["vehicle_type"].value_counts().idxmax(),
        "critical_zones":      int((zone_stats["priority"] == "CRITICAL").sum()),
    }
}

with open(OUT_DIR / "summary.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(f"      Saved: data/summary.json")

# ── FINAL REPORT ─────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("  PHASE 1 COMPLETE — KEY FINDINGS")
print("=" * 55)
print(f"  Total clean records  : {len(df_out):,}")
print(f"  Critical zones       : {(zone_stats['priority'] == 'CRITICAL').sum()}")
print(f"  Worst station        : {zone_stats.iloc[0]['police_station']}")
print(f"    └ violations       : {zone_stats.iloc[0]['total_violations']:,}")
print(f"    └ zone score       : {zone_stats.iloc[0]['zone_score']:.1f}/100")
print(f"    └ peak hour        : {int(zone_stats.iloc[0]['peak_hour']):02d}:00")
print(f"  Peak violation hour  : {int(df_out['hour'].value_counts().idxmax()):02d}:00")
print(f"  Top vehicle type     : {df_out['vehicle_type'].value_counts().idxmax()}")
print(f"  Top violation type   : {df_out['primary_violation'].value_counts().idxmax()}")
print("\n  Output files ready for Phase 2:")
print("    data/df_clean.csv   → full scored dataset")
print("    data/df_zones.csv   → zone-level aggregation")
print("    data/summary.json   → dashboard-ready JSON")
print("=" * 55)
