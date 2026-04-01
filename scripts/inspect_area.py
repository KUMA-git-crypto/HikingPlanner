import osmnx as ox
import networkx as nx

def inspect_area():
    graph_path = "data/sample_fuji.graphml"
    G = ox.load_graphml(graph_path)
    
    # Bounding box for Gotemba Ascent area (approx based on map)
    # The ascent/descent split is around 2500m-3000m
    north, south = 35.365, 35.355
    east, west = 138.755, 138.740
    
    print(f"Inspecting edges in box: N={north}, S={south}, E={east}, W={west}")
    
    count = 0
    for u, v, k, d in G.edges(keys=True, data=True):
        u_data = G.nodes[u]
        if south <= u_data['y'] <= north and west <= u_data['x'] <= east:
            count += 1
            name = d.get('name', 'N/A')
            highway = d.get('highway', 'N/A')
            oneway = d.get('oneway', 'no')
            access = d.get('access', 'N/A')
            level = d.get('level', 'N/A')
            
            # Check if it has a reverse edge
            has_rev = G.has_edge(v, u)
            
            print(f"Edge {u}-{v}: Name={name}, HW={highway}, 1way={oneway}, Access={access}, Rev={has_rev}")
            
    print(f"Total edges in box: {count}")

if __name__ == "__main__":
    inspect_area()
