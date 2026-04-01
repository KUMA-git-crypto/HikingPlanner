import osmnx as ox
import networkx as nx

def investigate():
    graph_path = "data/sample_fuji.graphml"
    print(f"Loading graph {graph_path}...")
    G = ox.load_graphml(graph_path)
    
    # Ikedakan approx coordinates (8th station)
    # Also search for '池田館' in nodes
    target_node = None
    for n, d in G.nodes(data=True):
        if 'name' in d and '池田館' in str(d['name']):
            print(f"Found node: {n}, Data: {d}")
            target_node = n
            break
            
    if not target_node:
        # Search by proximity if name not found
        lat, lon = 35.369, 138.736 # Near 8th station
        target_node = ox.distance.nearest_nodes(G, lon, lat)
        print(f"Found nearest node to (35.369, 138.736): {target_node}")
    
    print("\nEdges connected to this node:")
    for u, v, k, d in G.edges([target_node], keys=True, data=True):
        print(f"- Edge from {u} to {v} (key={k})")
        print(f"  Name: {d.get('name', 'N/A')}")
        print(f"  Highway: {d.get('highway', 'N/A')}")
        print(f"  Oneway: {d.get('oneway', 'N/A')}")
        print(f"  Other tags: { {k:v for k,v in d.items() if k not in ['geometry', 'name', 'highway', 'oneway', 'length']} }")

if __name__ == "__main__":
    investigate()
