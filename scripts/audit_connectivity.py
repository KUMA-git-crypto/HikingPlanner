import osmnx as ox
import networkx as nx

def audit_connectivity():
    graph_path = "data/sample_fuji.graphml"
    G = ox.load_graphml(graph_path)
    
    print(f"Auditing connectivity for {graph_path}...")
    
    # Check for disconnected components
    components = list(nx.weakly_connected_components(G))
    print(f"Number of weakly connected components: {len(components)}")
    
    # Sort components by size
    components.sort(key=len, reverse=True)
    for i, c in enumerate(components[:5]):
        print(f"  Component {i+1}: {len(c)} nodes")
        
    # Check for strongly connected components
    scc = list(nx.strongly_connected_components(G))
    print(f"Number of strongly connected components: {len(scc)}")
    scc.sort(key=len, reverse=True)
    print(f"  Largest SCC size: {len(scc[0])} nodes")

    # Check specifically for Gotemba Ascent reverse edges
    ascent_edges = []
    missing_reverse = 0
    total_ascent = 0
    for u, v, k, d in G.edges(keys=True, data=True):
        name = str(d.get('name', ''))
        if '御殿場' in name and '登り' in name:
            total_ascent += 1
            if not G.has_edge(v, u):
                missing_reverse += 1
    
    print(f"Gotemba Ascent: Total edges = {total_ascent}, Missing reverse = {missing_reverse}")
    
    # Check if they are in the largest SCC
    main_scc = scc[0]
    in_scc = 0
    total_nodes = 0
    seen_nodes = set()
    for u, v, k, d in G.edges(keys=True, data=True):
         name = str(d.get('name', ''))
         if '御殿場' in name and '登り' in name:
             for n in [u, v]:
                 if n not in seen_nodes:
                     total_nodes += 1
                     if n in main_scc:
                         in_scc += 1
                     seen_nodes.add(n)
    print(f"Gotemba Ascent nodes in main SCC: {in_scc} / {total_nodes}")

if __name__ == "__main__":
    audit_connectivity()
