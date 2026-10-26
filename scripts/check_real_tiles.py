#!/usr/bin/env python3
"""Check rare-year and small-fire records in a real local PMTiles archive."""
import gzip
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import geopandas as gpd
import mapbox_vector_tile
from pmtiles.reader import Reader, MmapSource
from firecan_fx import FIRE_DISPLAY_DATA_PATH, TOTALFIRE_DATA_PATH, fx_read_fire_geometry
from firecan_tiles import read_manifest


def main():
    manifest, archive = read_manifest()
    display = gpd.read_parquet(FIRE_DISPLAY_DATA_PATH)
    rare_year = display.fire_year.value_counts().sort_values().index[0]
    rare = display[display.fire_year == rare_year].index.tolist()[:5]
    # Select small positive fires; zero areas in source attributes need not
    # describe the actual polygon size. Every check uses original geometry.
    small = display[display.fire_size > 0].sort_values('fire_size').index.tolist()[:5]
    ids = sorted(set(rare + small))
    geometries = fx_read_fire_geometry(ids, TOTALFIRE_DATA_PATH).to_crs(4326)
    results = []
    with archive.open('rb') as source:
        reader = Reader(MmapSource(source))
        for row_id, geometry in geometries.items():
            point = geometry.representative_point()
            z = 14
            x = int((point.x + 180) / 360 * 2**z)
            y = int((1 - math.asinh(math.tan(math.radians(point.y))) / math.pi) / 2 * 2**z)
            found = []
            for tx in (x-1, x, x+1):
                for ty in (y-1, y, y+1):
                    raw = reader.get(z, tx, ty)
                    if raw:
                        found.extend(f for f in mapbox_vector_tile.decode(gzip.decompress(raw))['fires']['features'] if f['id'] == row_id)
            result = {'id': row_id, 'year': int(display.loc[row_id, 'fire_year']), 'size_ha': float(display.loc[row_id, 'fire_size']), 'fragments_at_z14': len(found)}
            results.append(result)
            if not found:
                raise AssertionError(f'Record missing near original interior point: {result}')
    print(json.dumps({'dataset_version': manifest['dataset_version'], 'rare_year': int(rare_year), 'samples': results}, indent=2))


if __name__ == '__main__':
    main()
