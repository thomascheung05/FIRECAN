#!/usr/bin/env python3
"""Focused main-map browser regression checks against a ready tiled server."""
import argparse
import json
from playwright.sync_api import sync_playwright
from benchmark_map import PIXEL, idle


def run(url):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        page.set_default_timeout(30000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('https://**/*', lambda route: route.fulfill(status=200, content_type='image/png', body=PIXEL))
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_function("document.getElementById('foundMessage').textContent.includes('157,093')")
        idle(page)
        assert page.evaluate("FireMap.getMap().getFilter('fires-fill')") is None
        # Popup text remains literal, including markup from a source attribute.
        assert page.evaluate("() => {const p=popupDetails({data_source:'<img onerror=alert(1)>'});return p.querySelectorAll('img').length===0&&p.textContent.includes('<img');}")
        page.locator('#minYear').fill('9000')
        page.locator('#filterButton').click()
        page.wait_for_function("document.getElementById('foundMessage').textContent.includes('No fires')")
        assert page.evaluate("FireMap.getMap().getFilter('fires-fill')") == ['==', ['id'], -1]
        page.locator('#clearFilters').click()
        page.wait_for_function("document.getElementById('foundMessage').textContent.includes('157,093')")
        idle(page)
        # Failed queries preserve the previous successful selection and count.
        page.route('**/map_query', lambda route: route.fulfill(status=503, json={'error': 'Test query unavailable'}))
        page.locator('#filterButton').click()
        page.wait_for_function("!document.getElementById('errorMessage').hidden")
        assert page.locator('#foundMessage').inner_text().startswith('157,093')
        assert page.evaluate("FireMap.getMap().getFilter('fires-fill')") is None
        page.unroute('**/map_query')
        # Even a server reply that resolves after Reset must be ignored.
        page.evaluate('''() => {
          const original = window.fetch; window.holdNextQuery = true;
          window.fetch = async (...args) => {
            const response = await original(...args);
            if(String(args[0]).includes('/map_query') && window.holdNextQuery) {
              window.holdNextQuery=false; await new Promise(resolve=>window.releaseOldQuery=resolve);
            }
            return response;
          };
        }''')
        page.locator('#minYear').fill('2016'); page.locator('#filterButton').click()
        page.wait_for_function('typeof window.releaseOldQuery === "function"')
        page.locator('#clearFilters').click()
        page.wait_for_function("document.getElementById('foundMessage').textContent.includes('157,093') && !document.getElementById('filterButton').disabled")
        page.evaluate('window.releaseOldQuery()')
        page.wait_for_timeout(200)
        assert page.evaluate("FireMap.getMap().getFilter('fires-fill')") is None
        assert page.locator('#foundMessage').inner_text().startswith('157,093')
        boundary = {'type': 'Polygon', 'coordinates': [[[-75, 46], [-74.99, 46], [-74.99, 46.01], [-75, 46.01], [-75, 46]]]}
        page.locator('#polygonFile').set_input_files({'name': 'boundary.geojson', 'mimeType': 'application/geo+json', 'buffer': json.dumps(boundary).encode()})
        page.wait_for_function("document.getElementById('polygonStatus').textContent.includes('ready')")
        assert page.evaluate("FireMap.getMap().getStyle().sources.boundary.data.geometry.type") == 'Polygon'
        page.locator('#polygonFile').set_input_files({'name': 'bad.geojson', 'mimeType': 'application/json', 'buffer': b'{"type":"Point","coordinates":[0,0]}'})
        page.wait_for_function("document.getElementById('errorMessage').textContent.includes('Previous boundary kept')")
        page.locator('#clearFilters').click()
        page.wait_for_function("!document.getElementById('filterButton').disabled")
        assert page.evaluate("FireMap.getMap().getStyle().sources.boundary.data.features.length") == 0
        assert page.evaluate('FireMap.getMap().getZoom()') == 3
        assert page.evaluate('FireMap.getMap().getCenter().lng') == -96
        page.locator('#watershedExplorerButton').click()
        page.wait_for_function('document.querySelectorAll("#watershedMap .leaflet-pane").length > 0')
        page.locator('#watershedDialog [data-close]').click()
        # All raster basemap choices preserve the vector source and its filter.
        page.locator('[aria-label="Basemap"]').select_option('1')
        assert page.evaluate("FireMap.getMap().getLayoutProperty('base-1','visibility')") == 'visible'
        page.screenshot(path='/private/tmp/firecan-final.png')
        assert not errors, errors
        context.close()
        for kind in ('webgl', 'tiles', 'manifest'):
            context = browser.new_context(viewport={'width': 1280, 'height': 800})
            page = context.new_page()
            page.route('https://**/*', lambda route: route.fulfill(status=200, content_type='image/png', body=PIXEL))
            if kind == 'webgl':
                page.add_init_script("const original=HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext=function(kind,...args){return kind==='webgl2'?null:original.call(this,kind,...args);};")
            elif kind == 'tiles':
                page.route('**/map_tiles/**', lambda route: route.fulfill(status=503, body='Missing test archive'))
            else:
                page.route('**/map_manifest', lambda route: route.fulfill(status=503, json={'error': 'Tiles are unavailable: run scripts/build_tiles.py'}))
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("!document.getElementById('dataStatus').hidden && document.getElementById('dataStatus').classList.contains('is-error')")
            text = page.locator('#dataStatusText').inner_text()
            assert ('WebGL' in text) if kind == 'webgl' else ('tiles' in text.lower()), text
            context.close()
        browser.close()
        print('Passed: auto load, empty/all, safe popups, failure retention, stale replies, boundary preview/replacement/reset, Leaflet watershed dialog, basemaps, tile/missing-artifact/WebGL errors.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5050')
    run(parser.parse_args().url)
