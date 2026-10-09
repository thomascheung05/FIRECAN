"""Small fixtures exercise filtering and HTTP exports without loading fire data."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Point, Polygon, box, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from firecan_fx import fx_filter_fires_data, parse_polygon_geojson
import firecan_fx


class FilteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fires = gpd.GeoDataFrame({
            'province': ['QC', 'ON', 'QC', 'QC'],
            'fire_year': [2000, 2010, 2020, 2021],
            'fire_size': [10, 20, 30, 40],
        }, geometry=[Polygon([(0, 0), (.5, -.05), (1, 0), (1, 1), (0, 1), (0, 0)]), box(2, 0, 3, 1), box(4, 0, 5, 1), box(8, 0, 9, 1)], crs=4326)
        cls.watersheds = gpd.GeoDataFrame({'watershed_name': ['TEST']}, geometry=[box(-1, -1, 6, 2)], crs=4326)
        # Patch only startup reads: routes and exporters run unchanged.
        spec = importlib.util.spec_from_file_location('firecan_test_app', ROOT / 'app/firecan_main.py')
        cls.module = importlib.util.module_from_spec(spec)
        with patch('geopandas.read_parquet', side_effect=[cls.fires.copy(), cls.watersheds.copy()]), \
             patch('pathlib.Path.exists', return_value=True):
            spec.loader.exec_module(cls.module)
        cls.client = cls.module.app.test_client()

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
        original = self.module.gdf_fires.geometry.to_wkb().tolist()
        response = self.client.post('/fx_main', json={'provinces': ['ALL'], 'polygon_tol': 50000})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(original, self.module.gdf_fires.geometry.to_wkb().tolist())
        self.assertNotEqual(shape(response.json["fires"]["features"][0]["geometry"]).wkb, original[0])
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
                self.assertEqual(exported.geometry.to_wkb().tolist(), original[:3])
        for payload in ({'watershed_name': 'UNKNOWN'}, {'download': 1, 'downloadFormat': 'bad'}, {'polygon_tol': -1}, {'provinces': 'QC'}, {'polygon_geojson': {'type': 'Point'}}):
            self.assertEqual(self.client.post('/fx_main', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/fx_main', data='{', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post('/fx_main', data='x' * (10 * 1024 * 1024 + 65537), content_type='application/json').status_code, 413)


    # ==== [EFFICIENCY UPDATE] gzip for large JSON and pages, never for attachments ====
    def test_gzip_responses(self):
        import gzip
        boundary = mapping(Point(0, 0).buffer(1, 256))
        response = self.client.post('/validate_polygon', json={'polygon_geojson': boundary}, headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(response.headers.get('Content-Encoding'), 'gzip')
        self.assertEqual(json.loads(gzip.decompress(response.data))['geometry']['type'], 'Polygon')
        page = self.client.get('/', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(page.headers.get('Content-Encoding'), 'gzip')
        self.assertIn(b'<html', gzip.decompress(page.data).lower())
        page.close()
        download = self.client.post('/fx_main', json={'download': 1, 'downloadFormat': 'csv'}, headers={'Accept-Encoding': 'gzip'})
        self.assertNotIn('Content-Encoding', download.headers)
    # ==== [END EFFICIENCY UPDATE] ====


# ==== [EFFICIENCY UPDATE] pre-computed display levels, geometry store and gzip ====
class DisplayDataTests(unittest.TestCase):
    def test_build_levels_store_and_exports(self):
        # Many-vertex circles so each display level visibly drops vertices.
        fires = gpd.GeoDataFrame({
            'province': ['QC', 'ON', 'QC', 'AB', 'QC'],
            'fire_year': [2000, 2005, 2010, 2015, 2020],
            'fire_size': [1.0, 2.0, 3.0, 4.0, 5.0],
        }, geometry=[Point(x, 50).buffer(.05, 256) for x in (-70, -80, -71, -115, -72)], crs=4326)
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(firecan_fx, 'BUILD_BATCH_SIZE', 2), patch.object(firecan_fx, 'STORE_ROW_GROUP_SIZE', 1):
            folder = Path(folder)
            source, display_path, store = folder / 'full.parquet', folder / 'display.parquet', folder / 'geometry.parquet'
            fires.to_parquet(source)
            firecan_fx.fx_build_display_data(source, display_path, store)
            display = gpd.read_parquet(display_path)

            # Fires are re-ordered spatially; each fire_id still pairs attributes with the right geometry.
            self.assertEqual(display['fire_id'].tolist(), [0, 1, 2, 3, 4])
            self.assertEqual(sorted(display['fire_year']), fires['fire_year'].tolist())
            source_row = display['fire_year'].map(dict(zip(fires['fire_year'], fires.index)))
            self.assertTrue(display.geometry.centroid.distance(gpd.GeoSeries(fires.geometry[source_row].values, index=display.index).centroid).max() < .01)
            vertices = [display[column].count_coordinates().sum() for column in ('geometry', 'geom_250', 'geom_1000')]
            self.assertLess(vertices[0], fires.count_coordinates().sum())
            self.assertGreater(vertices[0], vertices[1])
            self.assertGreaterEqual(vertices[1], vertices[2])

            # The store returns originals, in the requested order, reading only the needed row groups.
            originals = firecan_fx.fx_read_original_geometry([4, 1], store)
            self.assertEqual([g.wkb for g in originals], [fires.geometry[source_row[4]].wkb, fires.geometry[source_row[1]].wkb])

            subset = fx_filter_fires_data(display, None, ['QC'])['filtered_gdf']
            exported = firecan_fx.fx_export_frame(subset, store_path=store)
            self.assertEqual(list(exported.columns), ['province', 'fire_year', 'fire_size', 'geometry'])
            self.assertEqual(exported.geometry.to_wkb().tolist(), fires.geometry[source_row[subset.index]].to_wkb().tolist())
            self.assertNotIn('geometry', firecan_fx.fx_export_frame(subset, include_geometry=False, store_path=store).columns)

            # 300 m reuses the 250 m level; 10 m is finer than any level and falls back to the originals.
            shown = firecan_fx.fx_display_frame(subset, 300, store_path=store)
            self.assertEqual(list(shown.columns), ['province', 'fire_year', 'fire_size', 'geometry'])
            self.assertLessEqual(shown.count_coordinates().sum(), subset['geom_250'].count_coordinates().sum())
            fine = firecan_fx.fx_display_frame(subset, 10, store_path=store)
            self.assertGreater(fine.count_coordinates().sum(), subset.geometry.count_coordinates().sum())


# ==== [END EFFICIENCY UPDATE] ====


if __name__ == '__main__':
    unittest.main()
