from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import requests
import math
import os
import time

app = FastAPI(title="Hiking Trail API - Lightweight")
app.mount("/static", StaticFiles(directory="static"), name="static")

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
    "https://overpass.osm.ch/api/interpreter"
]

HIKING_FILTER = (
    "way['highway'~'path|footway|track|steps|pedestrian']"
    "['footway'!='sidewalk']['footway'!='crossing']['golf'!='cartpath']"
)
# Light connector roads: only used as bridges between trails, shown differently
CONNECTOR_FILTER = (
    "way['highway'~'service|unclassified|residential']"
    "['service'!='parking_aisle']['service'!='driveway']['service'!='alley']"
)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def fetch_from_overpass(query: str) -> dict:
    """Fetch with retries across multiple mirrors to avoid rate limiting."""
    for url in OVERPASS_URLS:
        for attempt in range(2):  # Two attempts per mirror
            try:
                r = requests.post(url, data={"data": query}, timeout=90)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 429: # Rate limit
                    print(f"Overpass rate limited ({url}), waiting 2s...")
                    time.sleep(2)
                    continue
                else:
                    print(f"Overpass Error {url}: {r.status_code} - {r.text[:100]}")
                    break # Try next mirror
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                print(f"Overpass Timeout/Connection error: {url}")
                break # Try next mirror
            except Exception as e:
                print(f"Overpass Exception {url}: {str(e)}")
                break
    raise HTTPException(status_code=503, detail="Overpass API (all mirrors) unavailable. Please try again later.")

def build_trail_data(osm_json: dict) -> dict:
    elements = osm_json.get("elements", [])
    nodes = {}  # str(id) -> [lat, lon]
    ways = []
    peaks = [] # list of {id, lat, lon, name}
    
    # 1. First pass: Collect all available nodes, peaks, and way objects
    for el in elements:
        if el["type"] == "node" and "lat" in el:
            nid_str = str(el["id"])
            nodes[nid_str] = [el["lat"], el["lon"]]
            tags = el.get("tags", {})
            if tags.get("natural") == "peak" or tags.get("place") == "peak":
                peaks.append({
                    "id": nid_str,
                    "lat": el["lat"],
                    "lon": el["lon"],
                    "name": tags.get("name", tags.get("name:ja", "山頂")),
                    "ele": float(tags.get("ele", 0)) if tags.get("ele") else 0
                })
        elif el["type"] == "node" and "tags" in el:
            # Collect other nodes that might have elevation info
            nid_str = str(el["id"])
            if nid_str not in nodes: # Already added in pass 1?
                nodes[nid_str] = [el["lat"], el["lon"]]
            # Store elevation in a separate dict if present
            ele = el["tags"].get("ele")
            if ele: nodes[nid_str + "_ele"] = float(ele)
        elif el["type"] == "way":
            ways.append(el)

    # 2. Second pass: Calculate junction nodes and trailhead types
    way_count = {} # nid -> total ways
    way_types = {} # nid -> set of types (0=hiking, 1=connector)
    endpoint_set = set()
    for w in ways:
        w_nodes = w.get("nodes", [])
        if not w_nodes: continue
        endpoint_set.add(str(w_nodes[0]))
        endpoint_set.add(str(w_nodes[-1]))
        
        highway = w.get("tags", {}).get("highway", "path")
        w_type = 1 if highway in ("service", "unclassified", "residential") else 0
        
        seen = set()
        for nid in w_nodes:
            snid = str(nid)
            # Track types intersecting at this node
            if snid not in way_types: way_types[snid] = set()
            way_types[snid].add(w_type)

            if snid not in seen:
                way_count[snid] = way_count.get(snid, 0) + 1
                seen.add(snid)

    # Trailheads are nodes where a hiking way (0) meets a connector way (1)
    trailhead_ids = set(
        nid for nid, types in way_types.items() 
        if 0 in types and 1 in types
    )
    
    junction_ids = set(nid for nid, cnt in way_count.items() if cnt >= 2) | endpoint_set

    # 3. Third pass: Build edges
    edges = []
    for w in ways:
        w_nodes = w.get("nodes", [])
        name = w.get("tags", {}).get("name", "")
        highway = w.get("tags", {}).get("highway", "path")
        oneway = w.get("tags", {}).get("oneway", "no")
        is_connector = highway in ("service", "unclassified", "residential")

        for i in range(len(w_nodes) - 1):
            u_id, v_id = str(w_nodes[i]), str(w_nodes[i + 1])
            if u_id in nodes and v_id in nodes:
                u_pos, v_pos = nodes[u_id], nodes[v_id]
                dist = haversine(u_pos[0], u_pos[1], v_pos[0], v_pos[1])
                e_data = {
                    "u": u_id, "v": v_id, "d": round(dist, 1), "name": name,
                    "c": [[u_pos[1], u_pos[0]], [v_pos[1], v_pos[0]]],
                    "t": 1 if is_connector else 0
                }
                edges.append(e_data)
                if oneway not in ("yes", "true", "1", "-1"):
                    edges.append({
                        "u": v_id, "v": u_id, "d": round(dist, 1), "name": name,
                        "c": [[v_pos[1], v_pos[0]], [u_pos[1], u_pos[0]]],
                        "t": 1 if is_connector else 0
                    })

    # 4. Final assembly
    referenced = {e["u"] for e in edges} | {e["v"] for e in edges}
    
    # Peak Snapping & Forced Inclusion
    # Ensure all peaks have node data even if not referenced yet
    for pk in peaks:
        pk_id = pk["id"]
        if pk_id not in nodes:
            nodes[pk_id] = [pk["lat"], pk["lon"]]
        
        # Snap if not referenced
        if pk_id in referenced: continue
        snap_candidates = list(junction_ids) if junction_ids else list(referenced)
        best_dist, best_node = 1500, None
        pk_pos = nodes[pk_id]
        for rid in snap_candidates:
            rpos = nodes[rid]
            if abs(pk_pos[0]-rpos[0]) > 0.015 or abs(pk_pos[1]-rpos[1]) > 0.015: continue
            d = haversine(pk_pos[0], pk_pos[1], rpos[0], rpos[1])
            if d < best_dist:
                best_dist, best_node = d, rid
        
        if best_node:
            edges.append({
                "u": pk_id, "v": best_node, "d": round(best_dist, 1), "name": "山頂への連絡",
                "c": [[pk_pos[1], pk_pos[0]], [nodes[best_node][1], nodes[best_node][0]]],
                "t": 0
            })
            edges.append({
                "u": best_node, "v": pk_id, "d": round(best_dist, 1), "name": "山頂への連絡",
                "c": [[nodes[best_node][1], nodes[best_node][0]], [pk_pos[1], pk_pos[0]]],
                "t": 0
            })
            referenced.add(pk_id)
        else:
            # Still include the peak node even if not connected!
            referenced.add(pk_id)

    filtered_nodes = {nid: nodes[nid] for nid in referenced if nid in nodes}
    # Add elevation suffix for frontend (Fix: avoiding dict mutation during iteration)
    ele_data = {}
    for nid in filtered_nodes:
        ele_key = nid + "_ele"
        if ele_key in nodes:
            ele_data[ele_key] = nodes[ele_key]
    filtered_nodes.update(ele_data)

    junctions = {nid for nid in junction_ids if nid in referenced}
    trailheads = {nid for nid in trailhead_ids if nid in referenced}

    return {
        "n": filtered_nodes, 
        "jn": list(junctions), 
        "th": list(trailheads),
        "pk": peaks,
        "e": edges
    }


@app.get("/")
def root():
    return {"status": "online", "usage": "/fetch-area?bbox=south,west,north,east"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/fetch-area")
def fetch_area(
    lat:    float = Query(..., description="Center latitude"),
    lon:    float = Query(..., description="Center longitude"),
    radius: float = Query(15.0, description="Radius in km (max 20)"),
):
    radius = min(radius, 20.0)
    around_meters = int(radius * 1000)
    # Reverting to the most stable multi-line Union query format
    query = (
        f"[out:json][timeout:60];"
        f"("
        f'  way(around:{around_meters},{lat},{lon})["highway"~"path|footway|track|steps|pedestrian"];'
        f'  way(around:{around_meters},{lat},{lon})["highway"~"service|unclassified|residential"];'
        f'  node(around:{around_meters},{lat},{lon})["natural"="peak"];'
        f'  node(around:{around_meters},{lat},{lon})["place"="peak"];'
        f");"
        f"(._;>;);"
        f"out;"
    )
    osm_data = fetch_from_overpass(query)
    trail_data = build_trail_data(osm_data)
    return trail_data


# Export endpoints (keep these — they are lightweight)
class RoutePoint(BaseModel):
    lat: float
    lon: float

class ExportData(BaseModel):
    name: str = "Hiking Route"
    points: List[RoutePoint]

@app.get("/get-elevation")
def get_elevation(lat: float, lon: float):
    try:
        url = f"https://msearch.gsi.go.jp/point-elevation/elevation.json?lon={lon}&lat={lat}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            ele = data.get("elevation")
            # GSI returns "----" for invalid/no-data areas
            if isinstance(ele, (int, float)): return {"elevation": float(ele)}
            try: return {"elevation": float(ele)}
            except: return {"elevation": 0.0}
        return {"elevation": 0.0}
    except:
        return {"elevation": 0.0}

@app.post("/export/gpx")
def export_gpx(data: ExportData):
    gpx = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="HikingPlanner" xmlns="http://www.topografix.com/GPX/1/1">',
        f'  <trk><name>{data.name}</name><trkseg>'
    ]
    for p in data.points:
        gpx.append(f'    <trkpt lat="{p.lat}" lon="{p.lon}"></trkpt>')
    gpx.append('  </trkseg></trk></gpx>')
    return Response(content="\n".join(gpx), media_type="application/gpx+xml",
                    headers={"Content-Disposition": f"attachment; filename={data.name}.gpx"})

@app.post("/export/kml")
def export_kml(data: ExportData):
    coords = " ".join([f"{p.lon},{p.lat},0" for p in data.points])
    kml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
        f'  <name>{data.name}</name><Placemark><LineString>',
        f'    <coordinates>{coords}</coordinates>',
        '  </LineString></Placemark></Document></kml>'
    ]
    return Response(content="\n".join(kml), media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": f"attachment; filename={data.name}.kml"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8021)
