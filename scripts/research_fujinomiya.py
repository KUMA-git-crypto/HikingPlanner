import osmnx as ox

def research_fujinomiya():
    # Fujinomiya trailhead
    center = (35.3344, 138.7285)
    dist = 1000 # 1km search
    
    print(f"Researching near Fujinomiya {center}...")
    
    # Get all network types to see what we might be missing
    G = ox.graph_from_point(center, dist=dist, network_type="all")
    
    print(f"Found {len(G.edges)} edges.")
    
    for u, v, k, d in G.edges(keys=True, data=True):
        highway = d.get('highway', 'N/A')
        name = d.get('name', 'N/A')
        
        # Look for things that might be the user's 'red dotted lines'
        # Often these are 'path' but might have specific tags
        print(f"\nEdge {u} -> {v} (key={k})")
        print(f"  Highway: {highway}")
        print(f"  Name: {name}")
        print(f"  Tags: { {k:v for k,v in d.items() if k not in ['geometry', 'name', 'highway']} }")

if __name__ == "__main__":
    research_fujinomiya()
