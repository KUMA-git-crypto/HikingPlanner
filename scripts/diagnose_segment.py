"""
Diagnose why a specific trail segment cannot be routed.
Targets the 半蔵坊 area on the Gotemba route (~lat 35.335, lon 138.757).
"""
import osmnx as ox
import networkx as nx

def diagnose():
    graph_path = "data/sample_fuji.graphml"
    G = ox.load_graphml(graph_path)
    
    # Compute main SCC (same as server does)
    scc_list = sorted(nx.strongly_connected_components(G), key=len, reverse=True)
    main_scc = scc_list[0]
    G_scc = G.subgraph(main_scc)
    
    print(f"Main SCC: {len(main_scc)} nodes")
    print()
    
    # The pointer location in the image (approx center of image)
    # 半蔵坊 area on Gotemba route
    # Try a range of candidate coordinates
    candidates = [
        (35.335, 138.757, "center of image (approx pointer)"),
        (35.332, 138.762, "lower-right junction (approx)"),
        (35.338, 138.752, "upper-left area"),
        (35.333, 138.755, "mid-trail point"),
    ]
    
    snapped_nodes = []
    for lat, lon, desc in candidates:
        nearest = ox.distance.nearest_nodes(G_scc, lon, lat)
        nd = G.nodes[nearest]
        print(f"{desc}:")
        print(f"  Input: ({lat:.4f}, {lon:.4f})")
        print(f"  Snapped node {nearest}: ({nd['y']:.5f}, {nd['x']:.5f})")
        # Get edges from this node
        out_edges = list(G.out_edges(nearest, data=True))
        print(f"  Out-edges: {len(out_edges)}")
        for u, v, d in out_edges[:3]:
            print(f"    -> {v}: name={d.get('name','?')}, highway={d.get('highway','?')}, access={d.get('access','?')}, length={d.get('length',0):.0f}m")
        snapped_nodes.append(nearest)
        print()
    
    # Try to route from pointer to lower-right junction
    start_node = snapped_nodes[0]
    end_node = snapped_nodes[1]
    
    print(f"Routing from {start_node} to {end_node}...")
    try:
        path = nx.shortest_path(G, start_node, end_node, 
                                weight=lambda u,v,d: d.get('length', 1))
        print(f"  Path found: {len(path)} nodes")
        # Show each segment
        for i in range(len(path)-1):
            u, v = path[i], path[i+1]
            edges = G.get_edge_data(u, v)
            best = min(edges.values(), key=lambda d: d.get('length', 1))
            print(f"  {u}->{v}: {best.get('name','?')} ({best.get('highway','?')}) len={best.get('length',0):.0f}m")
    except nx.NetworkXNoPath:
        print("  NO PATH FOUND!")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    # Also: scan the area for any disconnected edges
    print()
    print("Scanning all edges in area for access restrictions...")
    north, south = 35.345, 35.325
    east, west = 138.770, 138.745
    for u, v, k, d in G.edges(keys=True, data=True):
        ud = G.nodes[u]
        if south <= ud['y'] <= north and west <= ud['x'] <= east:
            access = d.get('access', '')
            name = d.get('name', '')
            if access in ['no', 'private'] or ('御殿場' in str(name)):
                has_rev = G.has_edge(v, u)
                u_in_scc = u in main_scc
                v_in_scc = v in main_scc
                print(f"  {u}->{v}: name={name}, hw={d.get('highway','?')}, access={access}, rev={has_rev}, u_scc={u_in_scc}, v_scc={v_in_scc}")

if __name__ == "__main__":
    diagnose()
