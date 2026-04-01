from fastapi import FastAPI, HTTPException, Response, Depends, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point
import uvicorn
import itertools
import os
import traceback
import threading
import sys

# Add scripts dir to path so we can import prep_data
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from prep_data import download_area, tile_key, tile_filename

app = FastAPI(title="Hiking Trail Snap API")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global graph state
G = None
G_simplified = None  # Cached simplified version for UI (edges)
main_scc_nodes = None  # Set of node IDs in the main strongly-connected component

# Area loading state (used by /area endpoint)
area_status = {
    "tile_key": None,
    "status": "idle",   # idle | loading | ready | error
    "message": ""
}
_area_lock = threading.Lock()

# Models for Export
class RoutePoint(BaseModel):
    lat: float
    lon: float

class ExportData(BaseModel):
    name: str = "Hiking Route"
    points: List[RoutePoint]

# Security middleware
API_KEY_ENV = os.getenv("API_KEY")

async def verify_api_key(api_key: Optional[str] = Query(None)):
    # If no API_KEY is set in environment, allow all requests
    if not API_KEY_ENV:
        return api_key
    # Otherwise, require a match
    if api_key != API_KEY_ENV:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid API Key")
    return api_key

def load_graph_from_file(graph_path: str):
    """Load a graphml file into the global variables. Returns True on success."""
    global G, G_simplified, main_scc_nodes
    print(f"Loading graph from {graph_path}...")
    g = ox.load_graphml(graph_path)
    print(f"Graph loaded: {len(g.nodes)} nodes. Computing SCC and simplifying...")
    
    scc_list = sorted(nx.strongly_connected_components(g), key=len, reverse=True)
    scc = scc_list[0]
    
    # Pre-simplify the graph for the UI to save RAM during /edges calls
    g_simp = ox.simplify_graph(g)
    
    G = g
    G_simplified = g_simp
    main_scc_nodes = scc
    print(f"Graph ready. Nodes: {len(G.nodes)}, Simplified Edges: {len(G_simplified.edges)}")
    return True


@app.on_event("startup")
def startup_event():
    # Try legacy fuji file first, then look for a tile file
    candidates = [
        "data/sample_fuji.graphml",
        tile_filename(*tile_key(35.3606, 138.7273)),
    ]
    for graph_path in candidates:
        if os.path.exists(graph_path):
            try:
                load_graph_from_file(graph_path)
                t_lat, t_lon = tile_key(35.3606, 138.7273)
                area_status["tile_key"] = f"{t_lat:.2f}_{t_lon:.2f}"
                area_status["status"] = "ready"
                area_status["message"] = f"Loaded {graph_path}"
            except Exception as e:
                print(f"CRITICAL ERROR loading graph: {e}")
                traceback.print_exc()
                area_status["status"] = "error"
                area_status["message"] = str(e)
            return
    print("WARNING: No default graph found. Area must be requested via /area endpoint.")

@app.get("/health")
def health():
    return {
        "status": "ok",
        "graph_loaded": G is not None,
        "area": area_status
    }

@app.get("/")
def read_root():
    return {
        "status": "online", 
        "message": "Hiking Trail Snap API is running",
        "features": {
            "area": "/area?lat=35.3606&lon=138.7273",
            "snap": "/snap?lat=35.3606&lon=138.7273",
            "route": "/route?start_lat=35.3606&start_lon=138.7273&end_lat=35.3644&end_lon=138.7307"
        }
    }

@app.get("/area/status")
def get_area_status():
    """Poll this to check if the area is ready after calling /area."""
    return area_status

@app.get("/area")
def load_area(lat: float, lon: float, api_key: str = Depends(verify_api_key)):
    """
    Request the server to load trail data for the area containing (lat, lon).
    If data is not cached, downloads it from OSM in the background.
    Returns immediately with status=loading or status=ready.
    """
    t_lat, t_lon = tile_key(lat, lon)
    new_key = f"{t_lat:.2f}_{t_lon:.2f}"

    with _area_lock:
        # Already loaded or loading this tile
        if area_status["tile_key"] == new_key:
            return area_status

        # New tile requested — start background download
        area_status["tile_key"] = new_key
        area_status["status"] = "loading"
        area_status["message"] = f"Preparing tile ({t_lat:.2f}, {t_lon:.2f})..."

    def _bg_load():
        try:
            def progress(msg):
                area_status["message"] = msg
                print(msg)

            filepath = download_area(lat, lon, on_progress=progress)
            area_status["message"] = "Loading graph into memory..."
            load_graph_from_file(filepath)
            with _area_lock:
                area_status["status"] = "ready"
                area_status["message"] = f"Ready: {len(G.nodes)} nodes."
        except Exception as e:
            with _area_lock:
                area_status["status"] = "error"
                area_status["message"] = str(e)
            traceback.print_exc()

    t = threading.Thread(target=_bg_load, daemon=True)
    t.start()
    return area_status

@app.get("/snap")
async def snap_point(lat: float, lon: float, api_key: str = Depends(verify_api_key)):
    if G is None or main_scc_nodes is None:
        raise HTTPException(status_code=503, detail="Graph not initialized.")
    
    try:
        # Build a view of G restricted to the main SCC so snapping never hits
        # an isolated node that can't participate in routing.
        G_scc = G.subgraph(main_scc_nodes)
        
        # Find nearest node inside the main SCC
        nearest = ox.distance.nearest_nodes(G_scc, lon, lat)
        node_data = G.nodes[nearest]
        
        return {
            "input": {"lat": lat, "lon": lon},
            "snapped": {
                "lat": node_data['y'],
                "lon": node_data['x'],
                "node_id": int(nearest)
            },
            "distance_m": ox.distance.great_circle(lat, lon, node_data['y'], node_data['x'])
        }
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

def get_edge_weight(u, v, d, G_local):
    """
    Calculate weight based on distance, hiker-friendliness, and direction.
    """
    length = d.get('length', 1.0)
    highway = d.get('highway', '')
    access = d.get('access', '')
    
    # Multiplier for the edge
    multiplier = 1.0
    
    u_data = G_local.nodes[u]
    v_data = G_local.nodes[v]
    # In Mt. Fuji area, latitude (y) is a good proxy for elevation. 
    # Center is high (35.36), periphery is low (35.31).
    # Going TOWARDS the center (35.36) is ASCENT.
    dist_u = abs(u_data['y'] - 35.3606)
    dist_v = abs(v_data['y'] - 35.3606)
    
    is_ascending = dist_v < dist_u 
    
    # Bonus for actual paths and steps
    if highway in ['path', 'steps'] or (isinstance(highway, list) and any(h in ['path', 'steps'] for h in highway)):
        multiplier *= 0.8 # Stronger bonus for hiker paths
        
    # Heavy penalty for restricted access
    if access in ['private', 'no']:
        multiplier *= 10.0
    
    return length * multiplier

@app.get("/route")
async def route_points(start_lat: float, start_lon: float, end_lat: float, end_lon: float, max_routes: int = 3, api_key: str = Depends(verify_api_key)):
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    
    try:
        # 1. Snap start and end to nearest node in main SCC
        G_scc = G.subgraph(main_scc_nodes)
        orig_node = ox.distance.nearest_nodes(G_scc, start_lon, start_lat)
        dest_node = ox.distance.nearest_nodes(G_scc, end_lon, end_lat)
        
        if orig_node == dest_node:
            raise HTTPException(status_code=400, detail="Start and end are the same point")
        
        # 2. Find shortest path using A*.
        # For heuristic, use great-circle distance between node positions.
        def heuristic(u, v):
            u_d = G.nodes[u]
            v_d = G.nodes[v]
            return ox.distance.great_circle(u_d['y'], u_d['x'], v_d['y'], v_d['x'])
        
        # For MultiDiGraph, weight must be a function (u, v, edge_data_dict)
        # edge_data_dict is a mapping of key -> data for all parallel edges.
        def weight_fn(u, v, edge_dict):
            # edge_dict is {key: {data}} for MultiDiGraph
            best = min(edge_dict.values(), key=lambda d: get_edge_weight(u, v, d, G))
            return get_edge_weight(u, v, best, G)
        
        path = nx.astar_path(G, orig_node, dest_node, heuristic=heuristic, weight=weight_fn)
        
        route_coords = []
        names_seen = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            edges = G.get_edge_data(u, v)
            if not edges:
                continue
            best_edge = min(edges.values(), key=lambda d: get_edge_weight(u, v, d, G))
            
            e_name = best_edge.get('name', 'Unnamed Trail')
            if isinstance(e_name, list):
                e_name = ", ".join(e_name)
            if not names_seen or names_seen[-1] != e_name:
                names_seen.append(e_name)

            if 'geometry' in best_edge:
                for x, y in best_edge['geometry'].coords:
                    route_coords.append({"lat": y, "lon": x})
            else:
                u_data = G.nodes[u]
                route_coords.append({"lat": u_data['y'], "lon": u_data['x']})
        
        # Add final node
        last = G.nodes[path[-1]]
        route_coords.append({"lat": last['y'], "lon": last['x']})
        
        # Deduplicate consecutive identical points
        unique_coords = []
        for p in route_coords:
            if not unique_coords or unique_coords[-1] != p:
                unique_coords.append(p)
        
        return {
            "start_node": int(orig_node),
            "end_node": int(dest_node),
            "count": 1,
            "alternatives": [{
                "node_count": len(path),
                "trail_names": names_seen,
                "route": unique_coords
            }]
        }

    except nx.NetworkXNoPath:
        raise HTTPException(status_code=404, detail="No route found between points")
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/export/gpx")
async def export_gpx(data: ExportData):
    gpx = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="HikingTrailSnap" xmlns="http://www.topografix.com/GPX/1/1">',
        f'  <trk><name>{data.name}</name><trkseg>'
    ]
    for p in data.points:
        gpx.append(f'    <trkpt lat="{p.lat}" lon="{p.lon}"></trkpt>')
    gpx.append('  </trkseg></trk></gpx>')
    
    return Response(content="\n".join(gpx), media_type="application/gpx+xml", 
                    headers={"Content-Disposition": f"attachment; filename={data.name}.gpx"})

@app.post("/export/kml")
async def export_kml(data: ExportData):
    coords = " ".join([f"{p.lon},{p.lat},0" for p in data.points])
    kml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '  <Document>',
        f'    <name>{data.name}</name>',
        '    <Placemark>',
        '      <LineString>',
        f'        <coordinates>{coords}</coordinates>',
        '      </LineString>',
        '    </Placemark>',
        '  </Document>',
        '</kml>'
    ]
    return Response(content="\n".join(kml), media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": f"attachment; filename={data.name}.kml"})

@app.get("/nodes")
def get_nodes(api_key: str = Depends(verify_api_key)):
    if G is None:
        return []
    
    nodes_data = []
    # A "through" node on any trail (oneway or bidirectional) has exactly 2
    # unique adjacent nodes (one on each side). Count both in AND out neighbors.
    for node, data in G.nodes(data=True):
        all_adjacent = set(G.predecessors(node)) | set(G.successors(node))
        if len(all_adjacent) != 2:
            nodes_data.append({
                "id": int(node),
                "lat": data['y'],
                "lon": data['x']
            })
    return nodes_data

@app.get("/edges")
def get_edges(api_key: str = Depends(verify_api_key)):
    if G is None:
        return []
    
    # PERFORMANCE: Use the pre-calculated simplified graph
    G_view = G_simplified
    
    if G_view is None:
        return []
    
    edges_data = []
    for u, v, k, d in G_view.edges(keys=True, data=True):
        if 'geometry' in d:
            geom = d['geometry']
            coords = list(geom.coords)
        else:
            u_data = G_view.nodes[u]
            v_data = G_view.nodes[v]
            coords = [(u_data['x'], u_data['y']), (v_data['x'], v_data['y'])]
        
        edges_data.append({
            "u": int(u),
            "v": int(v),
            "coords": [{"lat": c[1], "lon": c[0]} for c in coords],
            "name": d.get('name', 'N/A')
        })
    return edges_data

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8012)
