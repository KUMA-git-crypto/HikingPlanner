"""
prep_data.py - Download and cache OSM hiking trail data for a given area.
Can be used standalone or imported by the server for on-demand caching.
"""
import osmnx as ox
import os
import math
import argparse

CUSTOM_FILTER = '[\"highway\"~\"path|footway|track|steps|service|corridor|pedestrian\"]'
DOWNLOAD_RADIUS_M = 15000  # 15km radius per tile
TILE_GRID = 0.25           # 0.25 degree grid (~27km x 20km)
DATA_DIR = "data"


def tile_key(lat: float, lon: float) -> tuple[float, float]:
    """Round lat/lon to the nearest tile grid point."""
    t_lat = round(math.floor(lat / TILE_GRID) * TILE_GRID, 2)
    t_lon = round(math.floor(lon / TILE_GRID) * TILE_GRID, 2)
    return t_lat, t_lon


def tile_filename(t_lat: float, t_lon: float) -> str:
    return os.path.join(DATA_DIR, f"tile_{t_lat:.2f}_{t_lon:.2f}.graphml")


def download_area(lat: float, lon: float, on_progress=None) -> str:
    """
    Download hiking trail data around (lat, lon).
    Returns the path to the saved GraphML file.
    Raises on failure.
    """
    t_lat, t_lon = tile_key(lat, lon)
    filepath = tile_filename(t_lat, t_lon)

    if os.path.exists(filepath):
        if on_progress:
            on_progress(f"Cached tile found: {filepath}")
        return filepath

    os.makedirs(DATA_DIR, exist_ok=True)

    center = (t_lat + TILE_GRID / 2, t_lon + TILE_GRID / 2)  # center of tile cell
    if on_progress:
        on_progress(f"Downloading OSM data for tile ({t_lat:.2f}, {t_lon:.2f}), center={center}...")

    G = ox.graph_from_point(
        center,
        dist=DOWNLOAD_RADIUS_M,
        network_type="all",
        custom_filter=CUSTOM_FILTER,
        simplify=False
    )
    ox.save_graphml(G, filepath=filepath)

    if on_progress:
        on_progress(f"Saved {len(G.nodes)} nodes / {len(G.edges)} edges -> {filepath}")

    return filepath


def download_fuji():
    """Legacy: download the Fuji area."""
    # Fuji summit: 35.3606, 138.7273 → tile (35.25, 138.75)
    path = download_area(35.3606, 138.7273, on_progress=print)
    # Also keep legacy filename for backwards compat
    legacy = os.path.join(DATA_DIR, "sample_fuji.graphml")
    if not os.path.exists(legacy) and os.path.exists(path):
        import shutil
        shutil.copy(path, legacy)
        print(f"Also copied to legacy path: {legacy}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download hiking trail OSM data")
    parser.add_argument("--lat", type=float, default=35.3606, help="Latitude")
    parser.add_argument("--lon", type=float, default=138.7273, help="Longitude")
    args = parser.parse_args()
    download_area(args.lat, args.lon, on_progress=print)
