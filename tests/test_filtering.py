"""Small fixtures exercise filtering and HTTP exports without loading fire data."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Polygon, box, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from firecan_fx import fx_filter_fires_data, parse_polygon_geojson


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


if __name__ == '__main__':
    unittest.main()
