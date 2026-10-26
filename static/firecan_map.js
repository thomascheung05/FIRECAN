"use strict";
/* MapLibre/PMTiles main map; Leaflet remains scoped to the watershed dialog. */
const FireMap = (() => {
  let map;
  let manifest;
  let ready;
  const empty = () => ({ type: 'FeatureCollection', features: [] });
  const palette = { boundary: '#72d5d9', user_buffer: '#c4e8d5', watershed_polygon: '#a7bbeb' };
  const basemaps = {
    Satellite: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 'Tiles © Esri'],
    OpenStreetMap: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png', '© OpenStreetMap contributors'],
  };
  for (const [label, path] of Object.entries({ Cycle: 'cycle', Transport: 'transport', Landscape: 'landscape', Outdoors: 'outdoors', Spinal: 'spinal-map', 'Transport dark': 'transport-dark', Pioneer: 'pioneer', 'Mobile atlas': 'mobile-atlas', Neighbourhood: 'neighbourhood' })) {
    basemaps[label] = [`https://tile.thunderforest.com/${path}/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557`, '© Thunderforest, © OpenStreetMap contributors'];
  }
  function selectionFilter(selection) {
    if (selection.mode === 'all') return null;
    if (selection.mode === 'include' && !selection.ids.length) return ['==', ['id'], -1];
    const member = ['in', ['id'], ['literal', selection.ids]];
    return selection.mode === 'exclude' ? ['!', member] : member;
  }
  function initialize(onClick, onError) {
    const probe = document.createElement('canvas').getContext('webgl2');
    if (!window.maplibregl || !window.pmtiles || !probe) {
      throw new Error('This map needs WebGL. Enable hardware acceleration or use a browser with WebGL support.');
    }
    probe.getExtension('WEBGL_lose_context')?.loseContext();
    maplibregl.addProtocol('pmtiles', new pmtiles.Protocol().tile);
    const sources = {};
    const layers = [];
    Object.entries(basemaps).forEach(([name, [url, attribution]], index) => {
      sources[`base-${index}`] = { type: 'raster', tiles: [url], tileSize: 256, attribution, maxzoom: 19 };
      layers.push({ id: `base-${index}`, type: 'raster', source: `base-${index}`, layout: { visibility: index ? 'none' : 'visible' } });
    });
    map = new maplibregl.Map({ container: 'map', center: [-96, 58], zoom: 3, maxZoom: 18,
      style: { version: 8, sources, layers }, attributionControl: true, collectResourceTiming: true });
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
    const chooser = document.createElement('select');
    chooser.className = 'basemap-chooser';
    chooser.setAttribute('aria-label', 'Basemap');
    Object.keys(basemaps).forEach((name, index) => chooser.add(new Option(name, String(index))));
    chooser.addEventListener('change', () => Object.keys(basemaps).forEach((_, index) => map.setLayoutProperty(`base-${index}`, 'visibility', String(index) === chooser.value ? 'visible' : 'none')));
    map.addControl({ onAdd: () => chooser, onRemove: () => chooser.remove() }, 'top-right');
    map.on('error', event => {
      if (event.sourceId === 'fires' || /pmtiles|map_tiles/.test(event.error?.message || '')) onError('Could not load fire tiles. Check that local tile artifacts match the dataset, then reload.');
    });
    map.getCanvas().addEventListener('webglcontextlost', () => onError('The WebGL context was lost. Reload the page to restore the map.'));
    map.on('click', event => {
      const hits = map.getLayer('fires-fill') ? map.queryRenderedFeatures(event.point, { layers: ['fires-fill'] }) : [];
      const unique = [...new Map(hits.map(feature => [feature.id, feature])).values()];
      const content = onClick(unique, event.lngLat);
      new maplibregl.Popup().setLngLat(event.lngLat).setDOMContent(content).addTo(map);
    });
    ready = new Promise(resolve => map.once('style.load', () => {
      document.getElementById('map').setAttribute('aria-busy', 'false');
      document.getElementById('mapStartup').hidden = true;
      resolve();
    }));
    return map;
  }
  async function loadArchive(metadata) {
    await ready;
    manifest = metadata;
    map.addSource('fires', { type: 'vector', url: `pmtiles://${new URL(metadata.archive_url, location.origin).href}` });
    map.addLayer({ id: 'fires-fill', type: 'fill', source: 'fires', 'source-layer': metadata.layer,
      filter: ['==', ['id'], -1], paint: { 'fill-color': '#d8542c', 'fill-opacity': .42, 'fill-outline-color': '#ed8956' } });
    for (const [id, color] of Object.entries(palette)) {
      map.addSource(id, { type: 'geojson', data: empty() });
      map.addLayer({ id: `${id}-fill`, type: 'fill', source: id, paint: { 'fill-color': color, 'fill-opacity': .07 } });
      map.addLayer({ id: `${id}-line`, type: 'line', source: id, paint: { 'line-color': color, 'line-width': 2 } });
    }
    map.addSource('user_point', { type: 'geojson', data: empty() });
    map.addLayer({ id: 'user-point', type: 'circle', source: 'user_point', paint: { 'circle-radius': 6, 'circle-color': '#c4e8d5', 'circle-stroke-color': '#132c24', 'circle-stroke-width': 2 } });
  }
  function apply(data) {
    if (data.dataset_version !== manifest.dataset_version) throw new Error('The map dataset version changed. Reload the page.');
    // A layer filter persists for tiles fetched after subsequent pans and zooms.
    const start = performance.now();
    map.setFilter('fires-fill', selectionFilter(data.selection));
    for (const id of ['user_point', 'user_buffer', 'watershed_polygon']) map.getSource(id).setData(data[id] || empty());
    map.once('idle', () => { window.firecanLastApplyMs = performance.now() - start; });
  }
  function boundsOf(geometry) {
    const bounds = new maplibregl.LngLatBounds();
    function visit(coords) {
      if (typeof coords[0] === 'number') bounds.extend(coords);
      else coords.forEach(visit);
    }
    visit(geometry.coordinates);
    return bounds;
  }
  function boundary(geometry) {
    const bounds = geometry ? boundsOf(geometry) : null;
    if (geometry && bounds.isEmpty()) throw new Error('Boundary has no displayable geometry.');
    map.getSource('boundary').setData(geometry ? { type: 'Feature', properties: {}, geometry } : empty());
    if (bounds) map.fitBounds(bounds, { padding: { left: document.getElementById('filterPanel').hidden ? 20 : Math.min(360, map.getContainer().clientWidth / 2), top: 80, right: 35, bottom: 35 }, maxZoom: 12 });
  }
  return { initialize, loadArchive, apply, boundary, selectionFilter, resetView: () => map.jumpTo({ center: [-96, 58], zoom: 3 }), resize: () => map?.resize(), getMap: () => map };
})();
