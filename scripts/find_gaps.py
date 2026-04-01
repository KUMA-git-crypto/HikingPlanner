import osmnx as ox
import networkx as nx
from scipy.spatial import cKDTree
import numpy as np

def find_gaps():
    graph_path = "data/sample_fuji.graphml"
    G = ox.load_graphml(graph_path)
    
    print(f"Searching for gaps in {graph_path}...")
    
    # Get all nodes and their coordinates
    nodes_data = []
    node_ids = []
    for node, data in G.nodes(data=True):
        nodes_data.append([data['x'], data['y']])
        node_ids.append(node)
    
    tree = cKDTree(nodes_data)
    
    # Find nodes that are "Dead Ends" (degree 1)
    dead_ends = [n for n in G.nodes() if G.degree(n) <= 2] # 2 because it's DiGraph, so in+out=2 is a through-way
    # Better: specifically look for nodes with 0 outbound or 0 inbound edges
    disconnected = [n for n in G.nodes() if G.out_degree(n) == 0 or G.in_degree(n) == 0]
    
    print(f"Found {len(disconnected)} nodes with degree constraints.")
    
    gaps_found = 0
    for node in disconnected:
        u_data = G.nodes[node]
        # Find neighbors within ~20 meters (approx 0.0002 degrees)
        indices = tree.query_ball_point([u_data['x'], u_data['y']], 0.0002)
        
        for idx in indices:
            v_id = node_ids[idx]
            if v_id == node: continue
            
            # If they are NOT connected but are very close
            if not G.has_edge(node, v_id):
                v_data = G.nodes[v_id]
                # Double check distance in meters if possible, or just print
                gaps_found += 1
                if gaps_found < 20:
                    print(f"Gap: {node} -> {v_id} (Dist ~{0.0002*111000:.1f}m).")
                    
    print(f"Total potential gaps found: {gaps_found}")

if __name__ == "__main__":
    find_gaps()
