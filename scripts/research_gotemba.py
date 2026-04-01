import osmnx as ox

def research_gotemba():
    # Gotemba Route area (approx 1400m - 2000m)
    # Center near a known split point
    center = (35.325, 138.785)
    dist = 2000 
    
    print(f"Researching near Gotemba {center}...")
    
    # Get all network types
    G = ox.graph_from_point(center, dist=dist, network_type="all")
    
    print(f"Found {len(G.edges)} edges.")
    
    for u, v, k, d in G.edges(keys=True, data=True):
        name = d.get('name', 'N/A')
        highway = d.get('highway', 'N/A')
        oneway = d.get('oneway', 'N/A')
        
        if '御殿場' in str(name):
            print(f"\nEdge {u} -> {v} (key={k})")
            print(f"  Name: {name}")
            print(f"  Highway: {highway}")
            print(f"  Oneway: {oneway}")
            print(f"  Tags: { {k:v for k,v in d.items() if k not in ['geometry', 'name', 'highway', 'oneway']} }")

if __name__ == "__main__":
    research_gotemba()
