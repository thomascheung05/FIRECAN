#!/usr/bin/env python3
"""Real-data Chrome benchmark. Run a local FIRECAN tiled server first."""
import argparse
import base64
import json
import platform
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

PIXEL = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==')
CASES = [('Canada', {}), ('Quebec', {'provinces': ['QC']}),
         ('Canada 2016–2025', {'min_year': 2016, 'max_year': 2025}),
         ('Quebec 2016–2025', {'provinces': ['QC'], 'min_year': 2016, 'max_year': 2025}),
         ('Broad boundary', {'polygon_geojson': {'type': 'Polygon', 'coordinates': [[[-100, 40], [-50, 40], [-50, 65], [-100, 65], [-100, 40]]]}})]


def idle(page):
    page.evaluate('''() => new Promise((resolve,reject) => {
      const timer=setTimeout(()=>reject(new Error('Map did not become idle within 30 seconds')),30000);
      const done=()=>{clearTimeout(timer);resolve();};
      const map = FireMap.getMap();
      if (map.loaded()) requestAnimationFrame(() => requestAnimationFrame(done));
      else map.once('idle', () => requestAnimationFrame(() => requestAnimationFrame(done)));
    })''')


def measure(page, filters):
    return page.evaluate('''async filters => {
      const version = (await (await fetch('/map_manifest')).json()).dataset_version;
      const start = performance.now();
      const response = await fetch('/map_query', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...filters,dataset_version:version}) });
      const payload = await response.text();
      const data = JSON.parse(payload);
      if (!response.ok) throw new Error(data.error);
      const returned = performance.now();
      const renderStart = performance.now();
      FireMap.apply(data);
      await new Promise((resolve,reject) => {
        const timer=setTimeout(()=>reject(new Error('Selection did not become idle within 30 seconds')),30000);
        FireMap.getMap().once('idle', () => {clearTimeout(timer);requestAnimationFrame(() => requestAnimationFrame(resolve));});
      });
      return {count:data.count, mode:data.selection.mode, ids:data.selection.ids.length, query_json_bytes:new TextEncoder().encode(payload).length, query_ms:returned-start, apply_ms:performance.now()-renderStart, total_ms:performance.now()-start};
    }''', filters)


def run(url, headed=False, repeats=1):
    hardware = {'platform': platform.platform(), 'machine': platform.machine()}
    if platform.system() == 'Darwin':
        for field in ('machdep.cpu.brand_string', 'hw.memsize', 'hw.ncpu'):
            result = subprocess.run(['sysctl', '-n', field], capture_output=True, text=True)
            hardware[field] = result.stdout.strip() or result.stderr.strip()
    report = {'viewport': [1280, 800], 'hardware': hardware, 'cache': 'new browser context per case; OS disk cache warm; repeat in same context warm',
              'basemap': 'all external raster requests replaced with a local 1px image; external basemap latency excluded',
              'headless': not headed, 'results': []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=not headed)
        report['browser'] = browser.version
        browser_cdp = browser.new_browser_cdp_session()
        for repetition in range(repeats):
            for name, filters in CASES:
                print(f'Benchmarking {name}, repeat {repetition}', flush=True)
                context = browser.new_context(viewport={'width': 1280, 'height': 800})
                page = context.new_page()
                page.set_default_timeout(120000)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('https://**/*', lambda route: route.fulfill(status=200, content_type='image/png', body=PIXEL))
                cdp = context.new_cdp_session(page)
                cdp.send('Performance.enable')
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_function("document.getElementById('foundMessage').textContent.includes('matched')")
                idle(page)
                national_ms = page.evaluate('performance.now()')
                report['dataset_version'] = page.request.get(url.rstrip('/') + '/map_manifest').json()['dataset_version']
                cold_bytes = page.evaluate("performance.getEntriesByType('resource').filter(r=>r.name.includes('/map_tiles/')).reduce((s,r)=>s+r.transferSize,0)")
                cold = measure(page, filters)
                warm = measure(page, filters)
                metrics = {m['name']: m['value'] for m in cdp.send('Performance.getMetrics')['metrics']}
                # Animate through new tiles and zoom levels and sample frame intervals.
                pan = page.evaluate('''() => new Promise(resolve => {
                  const map = FireMap.getMap(); const times=[]; let previous=performance.now(); const start=previous;
                  let renders=0; const rendered=()=>renders++; map.on('render',rendered);
                  function frame(now) {
                    times.push(now-previous); previous=now;
                    if(now-start<2500) requestAnimationFrame(frame);
                    else { map.off('render',rendered); times.sort((a,b)=>a-b); resolve({fps:times.length/((now-start)/1000), map_render_fps:renders/((now-start)/1000), render_frames:renders, sample_ms:now-start, p95_frame_ms:times[Math.floor(times.length*.95)]}); }
                  }
                  map.easeTo({center:[-74,52],zoom:5,duration:2200});requestAnimationFrame(frame);
                })''')
                idle(page)
                # Membership must persist when the pan loads previously unseen tiles.
                visible = page.evaluate('''async filters => {
                  const manifest=await (await fetch('/map_manifest')).json();
                  const data=await (await fetch('/map_query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...filters,dataset_version:manifest.dataset_version})})).json();
                  const selected=new Set(data.selection.ids);
                  const fires=FireMap.getMap().queryRenderedFeatures({layers:['fires-fill']});
                  return {visible_fragments:fires.length, wrong_ids:fires.filter(f=> data.selection.mode==='include'?!selected.has(f.id):data.selection.mode==='exclude'?selected.has(f.id):false).length};
                }''', filters)
                processes = browser_cdp.send('SystemInfo.getProcessInfo')['processInfo']
                memory = subprocess.run(['ps', '-o', 'rss=', '-p', ','.join(str(p['id']) for p in processes)], capture_output=True, text=True)
                rss = sum(int(value) * 1024 for value in memory.stdout.split()) if memory.returncode == 0 else None
                result = {'case': name, 'repeat': repetition, 'cold_national_usable_ms': national_ms,
                          'cold_national_overlay_bytes': cold_bytes, 'cold_filter': cold, 'warm_filter': warm,
                          'js_heap_bytes': metrics.get('JSHeapUsedSize'), 'browser_rss_bytes': rss, **pan, **visible, 'errors': errors}
                report['results'].append(result)
                print(json.dumps(result), flush=True)
                context.close()
        browser.close()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5050')
    parser.add_argument('--headed', action='store_true')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--output', type=Path, default=Path('benchmark-results.json'))
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(args.url, args.headed, args.repeats), indent=2) + '\n')
