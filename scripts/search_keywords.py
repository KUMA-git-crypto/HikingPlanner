import osmnx as ox

def search_keywords():
    graph_path = "data/sample_fuji.graphml"
    G = ox.load_graphml(graph_path)
    
    keywords = ["ブル", "下山", "吉田", "須走", "登下山"]
    
    print("--- Searching for trail keywords ---")
    for u, v, k, d in G.edges(keys=True, data=True):
        name = str(d.get('name', ''))
        # Note: names might be encoded, but let's try to find patterns
        for kw in keywords:
            if kw in name:
                print(f"\nEdge {u}->{v} (key={k})")
                print(f"  Name: {name}")
                print(f"  Highway: {d.get('highway')}")
                print(f"  Oneway: {d.get('oneway')}")
                print(f"  Other: { {k:v for k,v in d.items() if k not in ['geometry', 'name']} }")
                break

if __name__ == "__main__":
    search_keywords()
