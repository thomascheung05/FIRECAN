"""Exact IDs, stateless version checks, HTTP byte ranges, streaming tile IDs."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from firecan_tiles import compact_selection, dataset_sources, dataset_version, file_identity
from firecan_fx import fx_filter_fires_data
import test_filtering
from build_tiles import write_sequence, build
from shapely.geometry import mapping, box


class MapQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_filtering.FilteringTests.setUpClass.__func__(cls)
        cls.module.FIRE_DISPLAY_DATA_PATH = cls.display_path
        cls.module.loaded_source_identity = (file_identity(cls.fire_path), file_identity(cls.display_path))
        cls.root = Path(cls.tmpdir.name) / 'tiles'
        cls.root.mkdir()
        sources = dataset_sources(cls.fire_path, cls.display_path)
        cls.version = dataset_version(sources)
        cls.archive = cls.root / cls.version / 'fires.pmtiles'
        cls.archive.parent.mkdir()
        cls.archive.write_bytes(b'PMTiles\x03' + bytes(range(256)) * 4)
        cls.manifest = {'dataset_version': cls.version, 'sources': sources, 'record_count': len(cls.display),
                        'archive_size': cls.archive.stat().st_size, 'bounds': [0, 0, 9, 1], 'layer': 'fires', 'minzoom': 0, 'maxzoom': 14}
        (cls.root / 'manifest.json').write_text(json.dumps(cls.manifest))
        cls.module.app.config['TILE_ROOT'] = str(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_exact_filters_and_spatial_semantics(self):
        cases = [{}, {'provinces': ['QC']}, {'min_year': 2010, 'max_year': 2020}, {'max_size': 25},
                 {'distance_coords': '0.5,4.5', 'distance_radius': 100}, {'watershed_name': 'TEST'},
                 {'polygon_geojson': mapping(box(.5, -.5, 4, 1.5))},
                 {'provinces': ['QC'], 'min_year': 2010, 'max_size': 35, 'watershed_name': 'TEST', 'polygon_geojson': mapping(box(.5, -.5, 4, 1.5))},
                 {'min_year': 9000}, {'provinces': []}]
        for params in cases:
            with self.subTest(params=params):
                expected = fx_filter_fires_data(self.display, self.watersheds, params.get('provinces', ['ALL']), geometry_source=self.fire_path,
                    **{k: v for k, v in params.items() if k != 'provinces'})
                response = self.client.post('/map_query', json={**params, 'dataset_version': self.version})
                self.assertEqual(response.status_code, 200, response.json)
                data = response.json
                self.assertEqual(data['count'], len(expected['filtered_gdf']))
                ids = set(data['selection']['ids'])
                if data['selection']['mode'] == 'all': ids = set(range(len(self.display)))
                elif data['selection']['mode'] == 'exclude': ids = set(range(len(self.display))) - ids
                self.assertEqual(ids, set(expected['filtered_gdf'].index))
                self.assertLessEqual(len(data['selection']['ids']), len(self.display) // 2)
                self.assertNotIn('fires', data)
                for key in ('user_point', 'user_buffer', 'watershed_polygon'):
                    self.assertIn(key, data)
                self.assertEqual(self.client.post('/map_query', json={**params, 'dataset_version': self.version}).json, data)
        # Intersection includes touching; containment excludes a straddling fire.
        boundary = mapping(box(.5, -.5, 4, 1.5))
        r = self.client.post('/map_query', json={'dataset_version': self.version, 'polygon_geojson': boundary})
        self.assertEqual(r.json['count'], 3)

    def test_versions_missing_artifacts_and_input(self):
        self.assertEqual(self.client.get('/map_manifest').json['dataset_version'], self.version)
        self.assertEqual(self.client.post('/map_query', json={'dataset_version': 'old'}).status_code, 409)
        for payload in ({}, [], {'dataset_version': 123}, {'dataset_version': self.version, 'provinces': 'QC'},
                        {'dataset_version': self.version, 'max_year': 'oops'}, {'dataset_version': self.version, 'watershed_name': 'unknown'},
                        {'dataset_version': self.version, 'polygon_geojson': {'type': 'Point'}}):
            self.assertEqual(self.client.post('/map_query', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/map_query', data='{', content_type='application/json').status_code, 400)
        with patch.dict(self.module.app.config, TILE_ROOT=str(self.root / 'missing')):
            self.assertEqual(self.client.get('/map_manifest').status_code, 503)
            self.assertEqual(self.client.post('/map_query', json={'dataset_version': self.version}).status_code, 503)
        with patch.object(self.module, 'loaded_source_identity', None):
            self.assertEqual(self.client.get('/map_manifest').status_code, 503)
        with patch.object(self.module, 'dataset_sources', return_value={}):
            self.assertEqual(self.client.get('/map_manifest').status_code, 503)
            self.assertEqual(self.client.post('/map_query', json={'dataset_version': self.version}).status_code, 503)
        with patch.dict(self.module.fire_data_status, state='checking'):
            self.assertEqual(self.client.get('/map_manifest').status_code, 503)

    def test_ranges_caching_and_legacy_switch(self):
        url = f'/map_tiles/{self.version}/fires.pmtiles'
        content = self.archive.read_bytes()
        for header, expected in [('bytes=0-126', content[:127]), ('bytes=127-255', content[127:256]), ('bytes=-10', content[-10:]), ('bytes=1000-', content[1000:])]:
            response = self.client.get(url, headers={'Range': header})
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, expected)
            self.assertIn('Content-Range', response.headers)
            self.assertNotIn('Content-Encoding', response.headers)
            response.close()
        response = self.client.get(url)
        self.assertEqual(response.data, content)
        self.assertIn('immutable', response.headers['Cache-Control'])
        etag = response.headers['ETag']; response.close()
        response = self.client.get(url, headers={'If-None-Match': etag})
        self.assertEqual(response.status_code, 304); response.close()
        response = self.client.head(url)
        self.assertEqual(int(response.headers['Content-Length']), len(content)); response.close()
        self.assertEqual(self.client.get(url, headers={'Range': 'bytes=9999-'}).status_code, 416)
        self.assertEqual(self.client.get('/map_tiles/bad/fires.pmtiles').status_code, 404)
        self.assertEqual(self.client.get('/map_tiles/' + '0'*64 + '/fires.pmtiles').status_code, 404)
        for renderer, asset in [('legacy', b'firecan_legacy.js'), ('tiles', b'firecan_map.js')]:
            with patch.dict(self.module.app.config, MAP_RENDERER=renderer):
                response = self.client.get('/')
                self.assertIn(asset, response.data); response.close()

    def test_sequence_physical_ids_and_attributes(self):
        path = Path(self.tmpdir.name) / 'source.geojsonseq'
        count, bounds = write_sequence(self.fire_path, path)
        features = [json.loads(row) for row in path.read_text().split('\x1e') if row.strip()]
        self.assertEqual(count, len(self.display))
        self.assertEqual([f['id'] for f in features], list(range(count)))
        self.assertEqual([f['properties']['fire_year'] for f in features], self.display.fire_year.tolist())
        self.assertNotIn('bbox_minx', features[0]['properties'])
        self.assertEqual(len(bounds), 4)
        self.assertEqual(compact_selection([], 0), {'mode': 'include', 'ids': []})

    def test_failed_build_preserves_published_manifest(self):
        before = (self.root / 'manifest.json').read_bytes()
        import subprocess
        with patch('build_tiles.shutil.which', return_value='/fake/tippecanoe'), patch('build_tiles.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'tippecanoe')):
            with self.assertRaises(subprocess.CalledProcessError):
                build(self.fire_path, self.display_path, self.root)
        self.assertEqual((self.root / 'manifest.json').read_bytes(), before)
        self.assertEqual(list(self.root.glob('.build-*')), [])


@unittest.skipUnless(os.environ.get('TIPPECANOE'), 'Set TIPPECANOE to run actual MVT fragment tests')
class TileIntegrationTests(unittest.TestCase):
    def test_fragments_rare_year_and_small_fire(self):
        import geopandas as gpd
        from firecan_fx import fx_build_fire_files
        from pmtiles.reader import Reader, MmapSource
        import mapbox_vector_tile
        import math
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fires = gpd.GeoDataFrame({'province': ['QC', 'QC'], 'fire_year': [1901, 2025], 'fire_size': [200, .1],
                                     'data_source': ['test', 'test'], 'data_aquisition': ['survey', 'survey']},
                                    geometry=[box(-.01, 49.99, .01, 50.01), box(.02, 50, .0202, 50.0002)], crs=4326)
            full, display = root / 'full.parquet', root / 'display.parquet'
            fx_build_fire_files(fires, full, display)
            with open(os.devnull, 'w') as log, patch('subprocess.run', wraps=__import__('subprocess').run) as run:
                # Tippecanoe stderr is kept available on failures by the command.
                manifest = build(full, display, root / 'tiles', os.environ['TIPPECANOE'])
            archive = root / 'tiles' / manifest['dataset_version'] / 'fires.pmtiles'
            counts = {}
            with archive.open('rb') as stream:
                reader = Reader(MmapSource(stream))
                self.assertEqual(reader.header()['max_zoom'], 14)
                for zoom in (10, 14):
                    y = int((1 - math.asinh(math.tan(math.radians(50))) / math.pi) / 2 * 2**zoom)
                    found = []
                    for x in range(2**(zoom-1)-1, 2**(zoom-1)+2):
                        for ty in (y-1, y, y+1):
                            raw = reader.get(zoom, x, ty)
                            if raw:
                                found.extend(mapbox_vector_tile.decode(gzip.decompress(raw))['fires']['features'])
                    self.assertTrue(all(isinstance(f['id'], int) for f in found))
                    for feature in found:
                        self.assertIn(feature['properties']['fire_year'], (1901, 2025))
                    counts[zoom] = found
                self.assertEqual({f['properties']['fire_year'] for f in counts[14]}, {1901, 2025})
                old_ids = [f['id'] for f in counts[14] if f['properties']['fire_year'] == 1901]
                self.assertGreater(len(old_ids), 1)
                self.assertEqual(len(set(old_ids)), 1)
                self.assertEqual({f['id'] for f in counts[10] if f['properties']['fire_year'] == 1901}, set(old_ids))
                self.assertTrue({f['id'] for f in counts[10]} <= {f['id'] for f in counts[14]})
