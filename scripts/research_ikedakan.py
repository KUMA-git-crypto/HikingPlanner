import osmnx as ox
import pandas as pd

def research_ikedakan_south():
    graph_path = "data/sample_fuji.graphml"
    print(f"Loading graph {graph_path}...")
    G = ox.load_graphml(graph_path)
    
    # Ikedakan approx: 35.3698, 138.7363
    # Look for edges south of it (smaller lat)
    # Box: 35.368 to 35.370, 138.735 to 138.738
    
    print("\n--- Edges South of Ikedakan (Bounding Box) ---")
    found = False
    for u, v, k, d in G.edges(keys=True, data=True):
        # Get coordinates of u or v (nodes)
        u_data = G.nodes[u]
        v_data = G.nodes[v]
        
        # Check if either node is in the box
        if 35.367 < u_data['y'] < 35.371 and 138.735 < u_data['x'] < 138.738:
            found = True
            print(f"\nEdge: {u} -> {v} (key={k})")
            print(f"  Name: {d.get('name', 'N/A')}")
            print(f"  Highway: {d.get('highway', 'N/A')}")
            print(f"  Oneway: {d.get('oneway', 'N/A')}")
            print(f"  Access: {d.get('access', 'N/A')}")
            print(f"  Motor Vehicle: {d.get('motor_vehicle', 'N/A')}")
            print(f"  Service: {d.get('service', 'N/A')}")
            print(f"  Other keys: {list(d.keys())}")
            
    if not found:
        print("No edges found in the specified bounding box.")

if __name__ == "__main__":
    research_ikedakan_south()
