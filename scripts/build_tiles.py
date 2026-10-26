#!/usr/bin/env python3
"""Explicit, streaming, atomic local PMTiles maintenance command."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely
from shapely.geometry import mapping
from firecan_fx import TOTALFIRE_DATA_PATH, FIRE_DISPLAY_DATA_PATH, fx_fire_files_ready
from firecan_tiles import TILE_ROOT, TILE_ATTRIBUTES, dataset_sources, dataset_version, fingerprint


def write_sequence(source, destination):
    """Hold at most one Parquet row group; IDs are physical row positions."""
    parquet = pq.ParquetFile(source)
    geo = json.loads(parquet.schema_arrow.metadata[b'geo'])
    column = geo['primary_column']
    crs = geo['columns'][column].get('crs', 'OGC:CRS84')
    offset = 0
    bounds = np.array([math.inf, math.inf, -math.inf, -math.inf])
    with open(destination, 'w') as output:
        for group in range(parquet.num_row_groups):
            table = parquet.read_row_group(group, columns=[column, *[a for a in TILE_ATTRIBUTES if a in parquet.schema_arrow.names]])
            rows = table.to_pandas()
            geometry = gpd.GeoSeries(shapely.from_wkb(rows.pop(column).to_numpy()), crs=crs).to_crs(4326)
            if geometry.isna().any() or geometry.is_empty.any() or not geometry.geom_type.isin(['Polygon', 'MultiPolygon']).all():
                raise ValueError('Every source row must have a nonempty polygon geometry.')
            b = geometry.total_bounds
            bounds[:2] = np.minimum(bounds[:2], b[:2])
            bounds[2:] = np.maximum(bounds[2:], b[2:])
            for position, geom in enumerate(geometry):
                properties = {a: (None if a not in rows or pd.isna(rows[a].iloc[position]) else rows[a].iloc[position]) for a in TILE_ATTRIBUTES}
                properties = {k: v.item() if isinstance(v, np.generic) else v for k, v in properties.items()}
                feature = {'type': 'Feature', 'id': offset + position, 'properties': properties, 'geometry': mapping(geom)}
                output.write('\x1e' + json.dumps(feature, separators=(',', ':'), allow_nan=False) + '\n')
            offset += len(rows)
            print(f'\rStreamed {offset:,} / {parquet.metadata.num_rows:,} fires', end='', flush=True)
    print()
    if not offset:
        raise ValueError('Cannot build tiles from an empty dataset.')
    return offset, bounds.tolist()


def build(full_path, display_path, output, tippecanoe='tippecanoe'):
    if not shutil.which(tippecanoe):
        raise ValueError('Install Tippecanoe >= 2.17 (brew install tippecanoe), or pass --tippecanoe PATH.')
    if not fx_fire_files_ready(full_path, display_path):
        raise ValueError('Original and display Parquet files must be a matched dataset.')
    sources = dataset_sources(full_path, display_path)
    version = dataset_version(sources)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Staging is on the publication filesystem; neither a partial archive nor a
    # partial manifest is ever visible. Old versions remain for existing tabs.
    with tempfile.TemporaryDirectory(prefix='.build-', dir=output) as staging:
        staging = Path(staging)
        sequence = staging / 'fires.geojsonseq'
        count, bounds = write_sequence(full_path, sequence)
        archive = staging / 'fires.pmtiles'
        command = [tippecanoe, '-o', str(archive), '-l', 'fires', '-Z0', '-z14',
                   '--drop-rate=1', '--no-feature-limit', '--no-tile-size-limit',
                   '--no-tiny-polygon-reduction', '--full-detail=12', '--low-detail=10', str(sequence)]
        subprocess.run(command, check=True)
        if dataset_sources(full_path, display_path) != sources:
            raise ValueError('Source changed during build; artifacts were not published.')
        manifest = {'dataset_version': version, 'sources': sources, 'record_count': count,
                    'bounds': bounds, 'layer': 'fires', 'minzoom': 0, 'maxzoom': 14,
                    'archive_size': archive.stat().st_size, 'archive_sha256': fingerprint(archive)['sha256'],
                    'tippecanoe': subprocess.check_output([tippecanoe, '--version'], stderr=subprocess.STDOUT, text=True).strip(),
                    'build_options': command[3:-1]}
        target = output / version
        if target.exists():
            # A version URL is immutable. Refuse to replace its bytes in place.
            existing = target / 'fires.pmtiles'
            if fingerprint(existing)['sha256'] != manifest['archive_sha256']:
                raise ValueError('This dataset version already has different tile bytes. Use a new output directory.')
        else:
            published = staging / 'published'
            published.mkdir()
            archive.replace(published / 'fires.pmtiles')
            (published / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            published.replace(target)
        temporary_manifest = staging / 'manifest.json'
        temporary_manifest.write_text(json.dumps(manifest, indent=2) + '\n')
        with temporary_manifest.open('rb') as stream:
            os.fsync(stream.fileno())
        temporary_manifest.replace(output / 'manifest.json')
    print(f'Published {version}: {count:,} fires, {manifest["archive_size"] / 1024**2:.2f} MiB')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=TOTALFIRE_DATA_PATH)
    parser.add_argument('--display', type=Path, default=FIRE_DISPLAY_DATA_PATH)
    parser.add_argument('--output', type=Path, default=TILE_ROOT)
    parser.add_argument('--tippecanoe', default='tippecanoe')
    args = parser.parse_args()
    try:
        build(args.source, args.display, args.output, args.tippecanoe)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'{exc}\n')
