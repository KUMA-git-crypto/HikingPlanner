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

app = FastAPI(title="Hiking Trail Snap API")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global variables for the graph
G = None
G_simple = None

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
    if API_KEY_ENV and api_key != API_KEY_ENV:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid API Key")
    return api_key

@app.on_event("startup")
def startup_event():
    global G, G_simple
    print("----------------------------------------")
    print("Initializing Hiking Trail Snap API...")
    graph_path = "data/sample_fuji.graphml"
    if os.path.exists(graph_path):
        print(f"DEBUG: Found graph file at {graph_path}")
        try:
            print(f"Loading graph from {graph_path}...")
            G = ox.load_graphml(graph_path)
            print(f"Graph loaded successfully: {len(G.nodes)} nodes, {len(G.edges)} edges.")
            
            # Pre-calculate simplified graph for routing to save memory during requests
            print("Pre-calculating simplified DiGraph...")
            G_simple = nx.DiGraph()
            for u, v, k, d in G.edges(keys=True, data=True):
                w = get_edge_weight(u, v, d)
                if G_simple.has_edge(u, v):
                    if w < G_simple[u][v]['weight']:
                        G_simple[u][v]['weight'] = w
                        G_simple[u][v]['data'] = d
                else:
                    G_simple.add_edge(u, v, weight=w, data=d)
            print("G_simple ready.")
        except Exception as e:
            print(f"CRITICAL ERROR loading graph: {e}")
    else:
        print(f"WARNING: Graph file NOT FOUND at {graph_path}")

@app.get("/health")
def health():
    return {"status": "ok", "graph_loaded": G is not None}

@app.get("/")
def read_root():
    return {
        "status": "online", 
        "message": "Hiking Trail Snap API is running",
        "features": {
            "snap": "/snap?lat=35.3606&lon=138.7273",
            "route": "/route?start_lat=35.3606&start_lon=138.7273&end_lat=35.3644&end_lon=138.7307"
        }
    }

@app.get("/snap")
async def snap_point(lat: float, lon: float, api_key: str = Depends(verify_api_key)):
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not initialized. Run data prep first.")
    
    try:
        # Find nearest edge (more precise than nearest node)
        # nearest_edges returns (u, v, key)
        u, v, k = ox.distance.nearest_edges(G, lon, lat)
        edge_data = G.get_edge_data(u, v, k)
        
        # Get the geometry of the edge
        # If 'geometry' key doesn't exist, it's a straight line between nodes
        if 'geometry' in edge_data:
            edge_geom = edge_data['geometry']
        else:
            from shapely.geometry import LineString
            u_data = G.nodes[u]
            v_data = G.nodes[v]
            edge_geom = LineString([(u_data['x'], u_data['y']), (v_data['x'], v_data['y'])])
        
        # Find the point on the edge nearest to the input (lon, lat)
        point = Point(lon, lat)
        # Use project and interpolate for exact snapping
        snapped_dist = edge_geom.project(point)
        snapped_point = edge_geom.interpolate(snapped_dist)
        
        return {
            "input": {"lat": lat, "lon": lon},
            "snapped": {
                "lat": snapped_point.y,
                "lon": snapped_point.x,
                "edge_nodes": [int(u), int(v)]
            },
            "distance_m": ox.distance.great_circle(lat, lon, snapped_point.y, snapped_point.x)
        }
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

def get_edge_weight(u, v, d):
    # Base weight is 'length'
    length = d.get('length', 1.0)
    highway = d.get('highway', '')
    access = d.get('access', '')
    
    multiplier = 1.0
    # Penalty for bulldozer-like roads (track)
    if highway == 'track' or (isinstance(highway, list) and 'track' in highway):
        multiplier *= 2.0
    # Heavy penalty for restricted access
    if access in ['private', 'no']:
        multiplier *= 10.0
    
    return length * multiplier

@app.get("/route")
async def route_points(start_lat: float, start_lon: float, end_lat: float, end_lon: float, max_routes: int = 3, api_key: str = Depends(verify_api_key)):
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    
    try:
        # 1. Snap start and end points
        orig_node = ox.distance.nearest_nodes(G, start_lon, start_lat)
        dest_node = ox.distance.nearest_nodes(G, end_lon, end_lat)
        
        # 2. Check for pre-calculated graph
        if G_simple is None:
             raise HTTPException(status_code=503, detail="Routing graph not ready")
        
        # 3. Calculate paths
        import itertools
        path_generator = nx.shortest_simple_paths(G_simple, orig_node, dest_node, weight='weight')
        
        results = []
        for path in itertools.islice(path_generator, max_routes):
            route_coords = []
            names_seen = []
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                edge_data = G_simple[u][v]['data']
                
                # Collect trail names
                e_name = edge_data.get('name', 'Unnamed Trail')
                if isinstance(e_name, list): e_name = ", ".join(e_name)
                if not names_seen or names_seen[-1] != e_name:
                    names_seen.append(e_name)

                if 'geometry' in edge_data:
                    for x, y in list(edge_data['geometry'].coords)[:-1]:
                        route_coords.append({"lat": y, "lon": x})
                else:
                    u_data = G.nodes[u]
                    route_coords.append({"lat": u_data['y'], "lon": u_data['x']})
            
            last_node = G.nodes[path[-1]]
            route_coords.append({"lat": last_node['y'], "lon": last_node['x']})
            
            results.append({
                "node_count": len(path),
                "trail_names": names_seen,
                "route": route_coords
            })
            
        return {
            "start_node": int(orig_node),
            "end_node": int(dest_node),
            "count": len(results),
            "alternatives": results
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
        raise HTTPException(status_code=503, detail="Graph not initialized")
    
    nodes_data = []
    # OSMnx graph nodes have 'y' (lat) and 'x' (lon) as attributes
    for node, data in G.nodes(data=True):
        nodes_data.append({
            "id": int(node),
            "lat": data['y'],
            "lon": data['x']
        })
    return nodes_data

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8012)
