import requests

r1 = requests.get('http://localhost:8012/snap?lat=35.335&lon=138.757')
r2 = requests.get('http://localhost:8012/snap?lat=35.328&lon=138.763')
print('Snap1:', r1.json())
print('Snap2:', r2.json())

r3 = requests.get('http://localhost:8012/route?start_lat=35.335&start_lon=138.757&end_lat=35.328&end_lon=138.763')
data = r3.json()
if 'alternatives' in data and data['alternatives']:
    alt = data['alternatives'][0]
    print(f"Route: {alt['node_count']} nodes, names={alt['trail_names']}")
    print("First 3 coords:")
    for c in alt['route'][:3]:
        print(' ', c)
    print("Last 3 coords:")
    for c in alt['route'][-3:]:
        print(' ', c)
else:
    print('Route response:', data)
