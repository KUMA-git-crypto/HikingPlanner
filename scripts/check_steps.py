import osmnx as ox

def check_for_steps():
    # Ikedakan approx: 35.3698, 138.7363
    center = (35.3698, 138.7363)
    dist = 500
    
    print(f"Checking for 'steps' near {center}...")
    
    # Try to download ONLY steps to see if they exist
    try:
        G_steps = ox.graph_from_point(center, dist=dist, network_type="all", custom_filter='["highway"="steps"]')
        print(f"Found {len(G_steps.edges)} step-type edges!")
        for u, v, k, d in G_steps.edges(keys=True, data=True):
            print(f"- Edge {u}->{v}: Name={d.get('name')}, OSMID={d.get('osmid')}")
    except Exception as e:
        print(f"No steps found or error: {e}")

    # Check the current graph to see if they are missing
    graph_path = "data/sample_fuji.graphml"
    G = ox.load_graphml(graph_path)
    steps_in_graph = [d for u,v,k,d in G.edges(keys=True, data=True) if d.get('highway') == 'steps']
    print(f"\nSteps currently in sample_fuji.graphml: {len(steps_in_graph)}")

if __name__ == "__main__":
    check_for_steps()
