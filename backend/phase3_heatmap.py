"""
Phase 3 — Heatmap Builder (Leap Year Overlap Fix & Aggressive Deduplication)
Flipkart Gridlock 2.0 | Parking Intelligence System
Run: python backend/phase3_heatmap.py
"""

import pandas as pd
import json
import folium
from folium.plugins import HeatMap, TimestampedGeoJson
from pathlib import Path

# ── CONFIG ───────────────────────────────────────────────────────────────────
DATA_DIR = Path("./data")
MAPS_DIR = Path("./maps")
MAPS_DIR.mkdir(exist_ok=True)

MAP_CENTER = [12.9716, 77.5946]
MAP_ZOOM   = 12

PRIORITY_COLORS = {
    "CRITICAL": "#E24B4A",
    "HIGH":     "#EF9F27",
    "MEDIUM":   "#639922",
    "LOW":      "#378ADD",
}

MONTH_ORDER = ["November", "December", "January", "February", "March"]

MONTH_DATES = {
    "November": "2023-11-01T00:00:00",
    "December": "2023-12-01T00:00:00",
    "January":  "2024-01-01T00:00:00",
    "February": "2024-02-01T00:00:00",
    "March":    "2024-03-01T00:00:00"
}

# ── LOAD & AGGRESSIVE DEDUPLICATE ────────────────────────────────────────────
print("=" * 55)
print("  PHASE 3 — HEATMAP BUILDER (CLEAN ZONES EDITION)")
print("=" * 55)

print("\n[1/4] Loading and cleaning Phase 2 outputs...")
df = pd.read_csv(DATA_DIR / "df_clusters.csv")

with open(DATA_DIR / "hotspots.json") as f:
    raw_hotspots = json.load(f)

with open(DATA_DIR / "patrol_schedule.json") as f:
    patrol = json.load(f)

# AGGRESSIVE SPATIAL DEDUPLICATION (Fixes concentric circles via coordinate merging)
unique_hotspots = {}
for h in raw_hotspots:
    # Rounding to 3 decimal places creates a ~110 meter grid to merge nearby overlaps
    coord_key = (round(h["centroid_lat"], 3), round(h["centroid_lng"], 3))
    
    # If location is new, or has a higher risk score than existing, keep the worst-case scenario
    if coord_key not in unique_hotspots or h.get("risk_score", 0) > unique_hotspots[coord_key].get("risk_score", 0):
        unique_hotspots[coord_key] = h

hotspots = list(unique_hotspots.values())

print(f"      df_clusters   : {len(df):,} rows")
print(f"      raw hotspots  : {len(raw_hotspots)} (contained overlaps)")
print(f"      clean hotspots: {len(hotspots)} (merged distinct zones)")

# ── MAP 1: DYNAMIC ZONES & STATIC BACKGROUND ─────────────────────────────────
print("\n[2/4] Building Dynamic Zones Animation...")

m1 = folium.Map(
    location=MAP_CENTER,
    zoom_start=MAP_ZOOM,
    tiles="CartoDB dark_matter",
)

sample_size = min(len(df), 10000)
sampled_df = df.sample(n=sample_size, random_state=42)
static_heat_data = sampled_df[["latitude", "longitude", "impact_score"]].values.tolist()

HeatMap(
    static_heat_data,
    radius=14,
    max_zoom=14,
    gradient={0.2: "#1a9850", 0.4: "#fee08b", 0.6: "#fd8d3c", 0.8: "#e24b4a", 1.0: "#800026"},
    min_opacity=0.1,
).add_to(m1)

monthly_features = []

for month in MONTH_ORDER:
    date_str = MONTH_DATES.get(month)
    month_df = df[df["month_name"] == month]
    
    for h in hotspots:
        near_mask = (abs(month_df['latitude'] - h['centroid_lat']) < 0.015) & \
                    (abs(month_df['longitude'] - h['centroid_lng']) < 0.015)
        
        local_vol = near_mask.sum()
        
        if local_vol < 10:
            continue
            
        if local_vol > 400:
            priority, radius = "CRITICAL", 25
        elif local_vol > 200:
            priority, radius = "HIGH", 20
        elif local_vol > 75:
            priority, radius = "MEDIUM", 15
        else:
            priority, radius = "LOW", 8
            
        color = PRIORITY_COLORS.get(priority, "#888")
        
        popup_html = f"""
        <div style='font-family:sans-serif;width:220px;'>
          <div style='background:{color};color:#fff;padding:8px 12px;border-radius:6px 6px 0 0;'>
            <b style='font-size:14px;'>{h['top_station']}</b><br>
            <span style='font-size:11px;opacity:.85;'>{month} — {priority}</span>
          </div>
          <div style='padding:10px 12px;background:#1a1a2e;color:#eee;border-radius:0 0 6px 6px;'>
            <table style='font-size:12px;width:100%;'>
              <tr><td style='color:#aaa;'>Monthly Violations</td><td style='text-align:right;'><b>{local_vol:,}</b></td></tr>
            </table>
          </div>
        </div>
        """
        
        monthly_features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [h["centroid_lng"], h["centroid_lat"]]
            },
            "properties": {
                "time": date_str,
                "popup": popup_html,
                "icon": "circle",
                "iconstyle": {
                    "fillColor": color,
                    "fillOpacity": 0.4,
                    "stroke": True,
                    "color": color,
                    "weight": 2,
                    "radius": radius
                }
            }
        })

geojson_data = {
    "type": "FeatureCollection",
    "features": monthly_features
}

TimestampedGeoJson(
    geojson_data,
    transition_time=400,
    period="P1M",
    duration="P27D", # LEAP YEAR FIX: Hard-kills the marker after 27 days so it cannot overlap into the next month
    add_last_point=False,
    auto_play=False,
    time_slider_drag_update=True
).add_to(m1)

title_html = """
<div style='position:absolute;top:12px;left:60px;z-index:1000;
     background:rgba(10,10,30,0.88);color:#fff;padding:10px 16px;
     border-radius:8px;border:1px solid rgba(255,255,255,0.15);
     font-family:sans-serif;'>
  <div style='font-size:15px;font-weight:600;'>ParkAlert Dynamic Zones</div>
  <div style='font-size:11px;opacity:.7;margin-top:2px;'>
    Nov 2023 – Mar 2024 · Clean Consolidated Zones
  </div>
</div>
"""
m1.get_root().html.add_child(folium.Element(title_html))

out1 = MAPS_DIR / "heatmap_live.html"
m1.save(str(out1))
print(f"      Saved: maps/heatmap_live.html")

# ── MAP 2: STATIC OVERVIEW & PATROL SCHEDULE ─────────────────────────────────
print("\n[3/4] Building static cluster overview map...")

m2 = folium.Map(
    location=MAP_CENTER,
    zoom_start=MAP_ZOOM,
    tiles="CartoDB positron",
)

# Full static heatmap background
all_points = df[["latitude", "longitude", "impact_score"]].values.tolist()

HeatMap(
    all_points,
    radius=12,
    max_zoom=14,
    gradient={0.2: "#1a9850", 0.5: "#fee08b", 0.75: "#fd8d3c", 1.0: "#e24b4a"},
    min_opacity=0.3,
).add_to(m2)

# Cluster circles with patrol schedule popup
for h, p in zip(hotspots, patrol):
    color  = PRIORITY_COLORS.get(h["priority"], "#888")
    radius = max(14, min(50, int(h["risk_score"] / 3)))

    windows_html = "".join([
        f"<tr><td style='color:#555;font-size:11px;'>{w['label']}</td>"
        f"<td style='text-align:right;font-size:11px;'>{w['impact']:,.0f}</td></tr>"
        for w in p["patrol_windows"]
    ])

    popup_html = f"""
    <div style='font-family:sans-serif;width:240px;'>
      <div style='background:{color};color:#fff;padding:8px 12px;border-radius:6px 6px 0 0;'>
        <b style='font-size:14px;'>{h['top_station']}</b><br>
        <span style='font-size:11px;opacity:.85;'>{h['priority']} · Score {h['risk_score']}/100</span>
      </div>
      <div style='padding:10px 12px;background:#fff;border-radius:0 0 6px 6px;'>
        <div style='font-size:11px;font-weight:600;color:#333;margin-bottom:6px;'>
          Recommended patrol windows
        </div>
        <table style='width:100%;'>
          <tr>
            <th style='font-size:10px;color:#888;text-align:left;'>Time window</th>
            <th style='font-size:10px;color:#888;text-align:right;'>Impact score</th>
          </tr>
          {windows_html}
        </table>
        <div style='margin-top:8px;padding-top:6px;border-top:1px solid #eee;font-size:11px;color:#555;'>
          Officers recommended: <b>{p['recommended_officers']}</b>
          &nbsp;|&nbsp; Peak hour: <b>{h['peak_hour']:02d}:00</b>
        </div>
      </div>
    </div>
    """

    folium.CircleMarker(
        location=[h["centroid_lat"], h["centroid_lng"]],
        radius=radius,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.3,
        weight=2.5,
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=f"[{h['priority']}] {h['top_station']} — click for patrol schedule",
    ).add_to(m2)

    # Label the cluster
    folium.Marker(
        location=[h["centroid_lat"], h["centroid_lng"]],
        icon=folium.DivIcon(
            html=f"""<div style='font-family:sans-serif;font-size:10px;font-weight:700;
                     color:{color};text-shadow:0 0 4px #fff,0 0 4px #fff;
                     white-space:nowrap;'>{h['top_station']}</div>""",
            icon_size=(120, 20),
            icon_anchor=(0, 20),
        ),
    ).add_to(m2)

out2 = MAPS_DIR / "heatmap_clusters.html"
m2.save(str(out2))
print(f"      Saved: maps/heatmap_clusters.html")

# ── FINAL REPORT ─────────────────────────────────────────────────────────────
print("\n[4/4] Done.")
print("\n" + "=" * 55)
print("  PHASE 3 COMPLETE")
print("=" * 55)