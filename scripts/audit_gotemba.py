import osmnx as ox

def audit_gotemba():
    graph_path = "data/sample_fuji.graphml"
    G = ox.load_graphml(graph_path)
    
    print(f"Auditing Gotemba trails in {graph_path}...")
    
    found = 0
    for u, v, k, d in G.edges(keys=True, data=True):
        name = d.get('name', '')
        # Handle list names
        if isinstance(name, list): name = " ".join([str(x) for x in name])
        
        if '御殿場' in str(name):
            found += 1
            print(f"\nEdge {u} -> {v}")
            print(f"  Name: {d.get('name')}")
            print(f"  Highway: {d.get('highway')}")
            print(f"  Oneway: {d.get('oneway')}")
            print(f"  Length: {d.get('length')}")
            
    print(f"\nTotal Gotemba related edges: {found}")

if __name__ == "__main__":
    audit_gotemba()
