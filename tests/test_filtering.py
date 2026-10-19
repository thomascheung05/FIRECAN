"""Small fixtures exercise filtering and HTTP exports without loading fire data."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Polygon, box, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import firecan_fx
from firecan_fx import (
    fx_build_fire_files, fx_fire_files_ready, fx_filter_fires_data, fx_load_fire_display, fx_read_fire_geometry, fx_with_full_geometry, parse_polygon_geojson,
)


class FilteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fires = gpd.GeoDataFrame({
            'province': ['QC', 'ON', 'QC', 'QC'],
            'fire_year': [2000, 2010, 2020, 2021],
            'fire_size': [10, 20, 30, 40],
        }, geometry=[Polygon([(0, 0), (.5, -.05), (1, 0), (1, 1), (0, 1), (0, 0)]), box(2, 0, 3, 1), box(4, 0, 5, 1), box(8, 0, 9, 1)], crs=4326)
        cls.watersheds = gpd.GeoDataFrame({'watershed_name': ['TEST']}, geometry=[box(-1, -1, 6, 2)], crs=4326)
        # Routes use fire files built the same way as the real dataset: a simplified copy in memory and full detail on disk.
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.fire_path = Path(cls.tmpdir.name) / 'fires.parquet'
        cls.display_path = Path(cls.tmpdir.name) / 'display.parquet'
        fx_build_fire_files(cls.fires, cls.fire_path, cls.display_path)
        cls.display = fx_load_fire_display(cls.display_path)
        # Patch only startup reads: routes and exporters run unchanged.
        spec = importlib.util.spec_from_file_location('firecan_test_app', ROOT / 'app/firecan_main.py')
        cls.module = importlib.util.module_from_spec(spec)
        with patch('geopandas.read_parquet', side_effect=[cls.watersheds.copy()]), \
             patch('pathlib.Path.exists', return_value=True):
            spec.loader.exec_module(cls.module)
        cls.module.TOTALFIRE_DATA_PATH = cls.fire_path
        cls.module.gdf_fires = cls.display
        cls.module.fire_data_status['state'] = 'ready'
        cls.client = cls.module.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def query(self, **filters):
        return fx_filter_fires_data(self.fires, self.watersheds, ['ALL'], **filters)['filtered_gdf']

    def test_overlap_touch_and_combined_filters(self):
        boundary = mapping(box(.5, -.5, 4, 1.5))
        self.assertEqual(self.query(polygon_geojson=boundary).index.tolist(), [0, 1, 2])
        self.assertEqual(self.query(polygon_geojson=boundary, min_year=2010, max_size=25).index.tolist(), [1])
        projected = self.fires.to_crs(3857)
        result = fx_filter_fires_data(projected, self.watersheds, ['QC'], polygon_geojson=boundary)
        self.assertEqual(result['filtered_gdf'].index.tolist(), [0, 2])
        self.assertTrue(self.query(polygon_geojson=mapping(box(50, 50, 51, 51))).empty)

    def test_display_copy_with_full_geometry_matches_in_memory(self):
        boundary = mapping(box(.5, -.5, 4, 1.5))
        for filters in ({}, {'min_year': 2010, 'max_size': 35}, {'polygon_geojson': boundary},
                        {'distance_coords': '0.5,4.5', 'distance_radius': 100}, {'watershed_name': 'TEST'},
                        {'polygon_geojson': boundary, 'distance_coords': '0.5,8.5', 'distance_radius': 10}):
            for provinces in (['ALL'], ['QC'], []):
                with self.subTest(filters=filters, provinces=provinces):
                    expected = fx_filter_fires_data(self.fires, self.watersheds, provinces, **filters)['filtered_gdf']
                    actual = fx_filter_fires_data(self.display, self.watersheds, provinces, geometry_source=self.fire_path, **filters)['filtered_gdf']
                    self.assertEqual(sorted(actual.fire_year), sorted(expected.fire_year))
                    self.assertNotIn('bbox_minx', actual.columns)

    def test_read_fire_geometry(self):
        full = gpd.read_parquet(self.fire_path)
        for ids in ([], [3], [2, 0], [0, 1, 2, 3]):
            with self.subTest(ids=ids):
                geoms = fx_read_fire_geometry(ids, self.fire_path)
                self.assertEqual(geoms.index.tolist(), ids)
                self.assertEqual(geoms.to_wkb().tolist(), full.geometry.iloc[ids].to_wkb().tolist())
        swapped = fx_with_full_geometry(self.display.iloc[[1, 3]], self.fire_path)
        self.assertEqual(swapped.geometry.to_wkb().tolist(), full.geometry.iloc[[1, 3]].to_wkb().tolist())

    def test_holes_and_multiple_features(self):
        hole = Polygon([(-1, -1), (6, -1), (6, 2), (-1, 2), (-1, -1)],
                       [[(1.5, -.5), (3.5, -.5), (3.5, 1.5), (1.5, 1.5), (1.5, -.5)]])
        document = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {}, 'geometry': mapping(hole)},
            {'type': 'Feature', 'properties': {}, 'geometry': mapping(box(7, -1, 10, 2))},
        ]}
        self.assertEqual(self.query(polygon_geojson=document).index.tolist(), [0, 2, 3])
        multi = {'type': 'MultiPolygon', 'coordinates': [mapping(box(-1, -1, 1.5, 2))['coordinates'], mapping(box(7, -1, 10, 2))['coordinates']]}
        self.assertEqual(self.query(polygon_geojson=multi).index.tolist(), [0, 3])

    def test_invalid_inputs(self):
        invalid = [None, {'type': 'Point', 'coordinates': [0, 0]},
                   {'type': 'FeatureCollection', 'features': []},
                   mapping(box(200, 0, 201, 1)),
                   {'type': 'Polygon', 'coordinates': [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]]}]
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(ValueError):
                parse_polygon_geojson(json.loads(json.dumps(document)))
        for filters in ({'watershed_name': 'UNKNOWN'}, {'min_year': 'oops'}, {'min_size': 50, 'max_size': 10}, {'distance_coords': '0,0'}, {'max_size': 'NaN'}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                self.query(**filters)
        self.assertEqual(len(self.query()), 4)

    def test_routes_simplification_and_exports(self):
        original = self.fires.geometry.to_wkb().tolist()
        response = self.client.post('/fx_main', json={'provinces': ['ALL'], 'polygon_tol': 50000})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(original), sorted(gpd.read_parquet(self.fire_path).geometry.to_wkb().tolist()))
        self.assertNotEqual(sorted(shape(f["geometry"]).wkb for f in response.json["fires"]["features"]), sorted(original))
        # Below the in-memory copy's tolerance the map starts from full detail.
        fine = self.client.post('/fx_main', json={'provinces': ['ALL'], 'polygon_tol': 0})
        self.assertEqual(sorted(shape(f["geometry"]).wkb for f in fine.json["fires"]["features"]), sorted(original))
        self.assertEqual(self.client.get('/fx_main').status_code, 200)
        boundary = mapping(box(.5, -.5, 4, 1.5))
        preview = self.client.post('/validate_polygon', json={'polygon_geojson': boundary})
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(shape(preview.json['geometry']).equals(shape(boundary)))
        self.assertEqual(self.client.post('/validate_polygon', json={'polygon_geojson': {'type': 'Point'}}).status_code, 400)
        for fmt in ('csv', 'json', 'gpkg'):
            response = self.client.post('/fx_main', json={'polygon_geojson': boundary, 'download': 1, 'downloadFormat': fmt})
            self.assertEqual(response.status_code, 200, response.data[:200])
            self.assertIn('attachment;', response.headers['Content-Disposition'])
            if fmt == 'csv':
                self.assertEqual(len(response.data.decode().splitlines()), 4)
            else:
                exported = gpd.read_file(io.BytesIO(response.data))
                self.assertEqual(len(exported), 3)
                self.assertEqual(sorted(exported.geometry.to_wkb().tolist()), sorted(original[:3]))
        for payload in ({'watershed_name': 'UNKNOWN'}, {'download': 1, 'downloadFormat': 'bad'}, {'polygon_tol': -1}, {'provinces': 'QC'}, {'polygon_geojson': {'type': 'Point'}}):
            self.assertEqual(self.client.post('/fx_main', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/fx_main', data='{', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get('/data_status').json, {'state': 'ready'})
        for state in ('downloading', 'error'):
            with patch.dict(self.module.fire_data_status, state=state):
                self.assertEqual(self.client.post('/fx_main', json={}).status_code, 503)
                self.assertEqual(self.client.get('/data_status').json, {'state': state})
        self.assertEqual(self.client.post('/fx_main', data='x' * (10 * 1024 * 1024 + 65537), content_type='application/json').status_code, 413)



class FireFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.fires = gpd.GeoDataFrame({
            'province': ['QC', 'ON', 'BC', 'AB'], 'fire_year': [2000, 2010, 2020, 2021], 'fire_size': [10, 20, 30, 40],
        }, geometry=[box(0, 0, 1, 1), box(20, 20, 21, 21), box(-40, 5, -39, 6), box(9, -30, 10, -29)], crs=4326)
        # Stand-in for the Git release, holding both built files
        self.release = self.tmp / 'release'
        self.release.mkdir()
        fx_build_fire_files(self.fires, self.release / 'TotalFire_data.parquet', self.release / 'TotalFire_display50m.parquet')
        self.processed = self.tmp / 'processed'
        self.processed.mkdir()
        self.full = self.processed / 'TotalFire_data.parquet'
        self.display = self.processed / 'TotalFire_display50m.parquet'

    def fake_download(self, url, filename, dest_dir):
        source = self.release / filename
        if not source.exists():
            return False
        shutil.copy(source, Path(dest_dir) / filename)
        return True

    def get_fire_data(self):
        with patch.object(firecan_fx, 'TOTALFIRE_DATA_PATH', self.full), \
             patch.object(firecan_fx, 'FIRE_DISPLAY_DATA_PATH', self.display), \
             patch.object(firecan_fx, 'PROCESSED_DATA_FOLDER_PATH', self.processed), \
             patch.object(firecan_fx, 'download_processed_data', side_effect=self.fake_download), \
             patch.object(firecan_fx, 'fx_download_raw_data', side_effect=RuntimeError('source download')), \
             patch.object(firecan_fx, 'fx_build_fire_files', wraps=fx_build_fire_files) as build:
            firecan_fx.fx_get_fire_data(download_from_git=True)
            return build

    def test_ready_needs_files_that_line_up(self):
        self.assertTrue(fx_fire_files_ready(self.release / 'TotalFire_data.parquet', self.release / 'TotalFire_display50m.parquet'))
        self.assertFalse(fx_fire_files_ready(self.full, self.display))
        # A full file whose rows are in a different order than the display copy, e.g. an older unsorted upload
        full = gpd.read_parquet(self.release / 'TotalFire_data.parquet')
        full.iloc[::-1].reset_index(drop=True).to_parquet(self.full)
        shutil.copy(self.release / 'TotalFire_display50m.parquet', self.display)
        self.assertFalse(fx_fire_files_ready(self.full, self.display))

    def test_git_download_uses_both_built_files(self):
        build = self.get_fire_data()
        build.assert_not_called()
        self.assertTrue(fx_fire_files_ready(self.full, self.display))

    def test_git_without_display_copy_builds_it(self):
        (self.release / 'TotalFire_display50m.parquet').unlink()
        build = self.get_fire_data()
        build.assert_called_once()
        self.assertTrue(fx_fire_files_ready(self.full, self.display))

    def test_git_with_mismatched_files_rebuilds(self):
        full = gpd.read_parquet(self.release / 'TotalFire_data.parquet')
        full.iloc[::-1].reset_index(drop=True).to_parquet(self.release / 'TotalFire_data.parquet')
        build = self.get_fire_data()
        build.assert_called_once()
        self.assertTrue(fx_fire_files_ready(self.full, self.display))

    def test_git_failure_falls_back_to_source(self):
        for name in ('TotalFire_data.parquet', 'TotalFire_display50m.parquet'):
            (self.release / name).unlink()
        with self.assertRaisesRegex(RuntimeError, 'source download'):
            self.get_fire_data()


if __name__ == '__main__':
    unittest.main()
