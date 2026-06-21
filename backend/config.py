"""
Shared configuration for Flask API.
"""

from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
MAPS_DIR = Path(__file__).parent.parent / "maps"

SUMMARY_FILE         = DATA_DIR / "summary.json"
HOTSPOTS_FILE         = DATA_DIR / "hotspots.json"
PATROL_SCHEDULE_FILE  = DATA_DIR / "patrol_schedule.json"
ZONES_FILE            = DATA_DIR / "df_zones.csv"
CLUSTERS_FILE         = DATA_DIR / "df_clusters.csv"

CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000","https://ai-traffic-management-flame.vercel.app"]

API_HOST = "0.0.0.0"
API_PORT = 5000
DEBUG    = True
