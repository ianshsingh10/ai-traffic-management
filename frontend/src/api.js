/**
 * API client — talks to the Flask backend on http://localhost:5000
 */

const BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:5000";

async function get(path) {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  getSummary:   ()              => get("/api/summary"),
  getZones:     (priority)      => get(priority ? `/api/zones?priority=${priority}` : "/api/zones"),
  getHotspots:  (priority)      => get(priority ? `/api/hotspots?priority=${priority}` : "/api/hotspots"),
  getSchedule:  (clusterId)     => get(clusterId != null ? `/api/schedule?cluster_id=${clusterId}` : "/api/schedule"),
  getTrends:    ()              => get("/api/trends"),
  getViolations:(clusterId, limit = 50, offset = 0) =>
    get(`/api/violations?${clusterId != null ? `cluster_id=${clusterId}&` : ""}limit=${limit}&offset=${offset}`),
};
