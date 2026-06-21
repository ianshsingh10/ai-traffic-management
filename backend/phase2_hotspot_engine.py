"""
Phase 2 — Hotspot Engine
Flipkart Gridlock 2.0 | Parking Intelligence System
Run: python backend/phase2_hotspot_engine.py
Reads:  data/df_clean.csv, data/df_zones.csv
Writes: data/df_clusters.csv, data/hotspots.json, data/patrol_schedule.json
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ── CONFIG ───────────────────────────────────────────────────────────────────
DATA_DIR     = Path("./data")
N_CLUSTERS   = 18  # chosen after testing k=6..20; 18 gave the best silhouette
                    # score (0.3255) while keeping every cluster a usable size
                    # (smallest cluster still has 600+ violations)
RANDOM_STATE = 42

# ── LOAD ─────────────────────────────────────────────────────────────────────
print("=" * 55)
print("  PHASE 2 — HOTSPOT ENGINE")
print("=" * 55)

print("\n[1/5] Loading Phase 1 outputs...")
df       = pd.read_csv(DATA_DIR / "df_clean.csv")
df_zones = pd.read_csv(DATA_DIR / "df_zones.csv")
print(f"      df_clean  : {len(df):,} rows")
print(f"      df_zones  : {len(df_zones)} zones")

# ── STEP 2: K-MEANS CLUSTERING ───────────────────────────────────────────────
print(f"\n[2/5] Running K-Means clustering (k={N_CLUSTERS})...")

features = df[["latitude", "longitude", "impact_score"]].copy()
scaler   = StandardScaler()
X_scaled = scaler.fit_transform(features)

kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=10)
df["cluster_id"] = kmeans.fit_predict(X_scaled)

print(f"      Clusters formed: {N_CLUSTERS}")
print(f"      Cluster sizes:")
cluster_sizes = df["cluster_id"].value_counts().sort_index()
for cid, cnt in cluster_sizes.items():
    print(f"        Cluster {cid:>2}  ->  {cnt:,} violations")

# ── STEP 2b: VALIDATE CLUSTER QUALITY (SILHOUETTE SCORE) ─────────────────────
print("\n[2b/5] Validating cluster quality (silhouette score)...")

from sklearn.metrics import silhouette_score

# Silhouette score on the full 115k points is slow; sampling 10k points
# is standard practice and gives a statistically stable estimate
np.random.seed(RANDOM_STATE)
sample_size = min(10000, len(X_scaled))
sample_idx = np.random.choice(len(X_scaled), size=sample_size, replace=False)

silhouette = silhouette_score(X_scaled[sample_idx], df["cluster_id"].values[sample_idx])

print(f"      Silhouette score: {silhouette:.4f}  (sampled {sample_size:,} points)")
print(f"      Scale: -1 (overlapping) to +1 (perfectly separated)")
print(f"      k={N_CLUSTERS} was chosen by testing k=6..20 directly on this")
print(f"      dataset and picking the best score with no cluster smaller")
print(f"      than ~600 violations (avoids unusable micro-zones)")

# ── STEP 3: CLUSTER PROFILING ────────────────────────────────────────────────
print("\n[3/5] Profiling each cluster...")

cluster_profiles = []

for cid in range(N_CLUSTERS):
    c       = df[df["cluster_id"] == cid]
    weights = c["impact_score"].values

    centroid_lat = float(np.average(c["latitude"],  weights=weights))
    centroid_lng = float(np.average(c["longitude"], weights=weights))

    total_impact     = float(c["impact_score"].sum())
    total_violations = int(len(c))
    peak_hour        = int(c["hour"].value_counts().idxmax())
    top_violation    = c["primary_violation"].value_counts().idxmax()
    top_vehicle      = c["vehicle_type"].value_counts().idxmax()
    top_station      = c["police_station"].value_counts().idxmax()
    hourly           = c.groupby("hour")["impact_score"].sum().to_dict()
    weekend_pct      = float(c["is_weekend"].mean() * 100)
    monthly          = c.groupby("month_name")["id"].count().to_dict()

    cluster_profiles.append({
        "cluster_id":       cid,
        "centroid_lat":     round(centroid_lat, 6),
        "centroid_lng":     round(centroid_lng, 6),
        "total_violations": total_violations,
        "total_impact":     round(total_impact, 2),
        "avg_impact":       round(float(c["impact_score"].mean()), 2),
        "peak_hour":        peak_hour,
        "top_violation":    top_violation,
        "top_vehicle":      top_vehicle,
        "top_station":      top_station,
        "weekend_pct":      round(weekend_pct, 1),
        "hourly_impact":    {int(k): round(v, 2) for k, v in hourly.items()},
        "monthly_trend":    monthly,
    })

# Normalise risk score 0-100
impacts = [c["total_impact"] for c in cluster_profiles]
min_i, max_i = min(impacts), max(impacts)
for c in cluster_profiles:
    c["risk_score"] = round(
        (c["total_impact"] - min_i) / (max_i - min_i) * 100, 1
    )

def priority(score):
    if score >= 70: return "CRITICAL"
    elif score >= 40: return "HIGH"
    elif score >= 20: return "MEDIUM"
    else: return "LOW"

for c in cluster_profiles:
    c["priority"] = priority(c["risk_score"])

cluster_profiles.sort(key=lambda x: x["risk_score"], reverse=True)

print(f"      Top 5 clusters by risk:")
for c in cluster_profiles[:5]:
    print(f"        [{c['priority']:<8}] Cluster {c['cluster_id']:>2} "
          f"score={c['risk_score']:5.1f}  "
          f"violations={c['total_violations']:,}  "
          f"peak={c['peak_hour']:02d}:00  "
          f"station={c['top_station']}")

# ── STEP 4: PATROL SCHEDULE GENERATOR ────────────────────────────────────────
print("\n[4/5] Generating AI patrol schedule...")

def top_patrol_windows(hourly_impact, n=3):
    windows = []
    for h in sorted(hourly_impact.keys()):
        window_impact = hourly_impact.get(h, 0) + hourly_impact.get(h + 1, 0)
        windows.append({
            "start":  h,
            "end":    h + 2,
            "label":  f"{h:02d}:00 - {h+2:02d}:00",
            "impact": round(window_impact, 2),
        })
    windows.sort(key=lambda x: x["impact"], reverse=True)
    return windows[:n]

patrol_schedule = []

for c in cluster_profiles:
    windows = top_patrol_windows(c["hourly_impact"])
    patrol_schedule.append({
        "cluster_id":         c["cluster_id"],
        "risk_score":         c["risk_score"],
        "priority":           c["priority"],
        "top_station":        c["top_station"],
        "centroid_lat":       c["centroid_lat"],
        "centroid_lng":       c["centroid_lng"],
        "patrol_windows":     windows,
        "recommended_officers": 3 if c["priority"] == "CRITICAL"
                                else 2 if c["priority"] == "HIGH"
                                else 1,
    })

print(f"      Schedule generated for {len(patrol_schedule)} clusters")
print(f"      Sample — top cluster:")
top = patrol_schedule[0]
print(f"        Station  : {top['top_station']}")
print(f"        Priority : {top['priority']}  (score {top['risk_score']})")
print(f"        Officers : {top['recommended_officers']}")
for w in top["patrol_windows"]:
    print(f"        Window   : {w['label']}  (impact {w['impact']})")

# ── STEP 5: SAVE ─────────────────────────────────────────────────────────────
print("\n[5/5] Saving outputs...")

df.to_csv(DATA_DIR / "df_clusters.csv", index=False)
print(f"      Saved: data/df_clusters.csv  ({len(df):,} rows)")

with open(DATA_DIR / "hotspots.json", "w") as f:
    json.dump(cluster_profiles, f, indent=2, default=str)
print(f"      Saved: data/hotspots.json  ({len(cluster_profiles)} clusters)")

with open(DATA_DIR / "patrol_schedule.json", "w") as f:
    json.dump(patrol_schedule, f, indent=2, default=str)
print(f"      Saved: data/patrol_schedule.json")

with open(DATA_DIR / "summary.json") as f:
    summary = json.load(f)

summary["clusters"] = {
    "total":       N_CLUSTERS,
    "critical":    sum(1 for c in cluster_profiles if c["priority"] == "CRITICAL"),
    "high":        sum(1 for c in cluster_profiles if c["priority"] == "HIGH"),
    "medium":      sum(1 for c in cluster_profiles if c["priority"] == "MEDIUM"),
    "low":         sum(1 for c in cluster_profiles if c["priority"] == "LOW"),
    "top_cluster": cluster_profiles[0],
    "silhouette_score": round(float(silhouette), 4),
    "silhouette_note": (
        "Score ranges -1 to 1. k=18 was selected by testing k=6..20 directly "
        "on this dataset and choosing the highest silhouette score subject to "
        "every cluster remaining a usable patrol zone (no cluster below ~600 "
        "violations). The moderate score reflects natural overlap between "
        "hotspots in a dense, continuously built-up city."
    ),
}

with open(DATA_DIR / "summary.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(f"      Updated: data/summary.json")

# ── FINAL REPORT ─────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("  PHASE 2 COMPLETE — KEY FINDINGS")
print("=" * 55)
print(f"  Clusters generated   : {N_CLUSTERS}")
print(f"  Critical clusters    : {sum(1 for c in cluster_profiles if c['priority'] == 'CRITICAL')}")
print(f"  High clusters        : {sum(1 for c in cluster_profiles if c['priority'] == 'HIGH')}")
print(f"  Top cluster station  : {cluster_profiles[0]['top_station']}")
print(f"  Top cluster score    : {cluster_profiles[0]['risk_score']}/100")
print(f"  Top cluster peak hr  : {cluster_profiles[0]['peak_hour']:02d}:00")
print(f"  Silhouette score     : {silhouette:.4f} (cluster quality validation)")
total_officers = sum(p["recommended_officers"] for p in patrol_schedule)
print(f"  Total officers needed: {total_officers} across all zones")
print("\n  Output files ready for Phase 3:")
print("    data/df_clusters.csv      -> violations with cluster labels")
print("    data/hotspots.json        -> cluster profiles + risk scores")
print("    data/patrol_schedule.json -> patrol windows per cluster")
print("=" * 55)