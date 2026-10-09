"use strict";

 var Esrimap = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 18, attribution: 'Tiles © Esri', name: "Esrimap"  }
); 
var OpenStreetMap_Mapnik = L.tileLayer(
  'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "OpenStreetMap_Mapnik" }
); 
var OpenCycleMap = L.tileLayer(
  'https://tile.thunderforest.com/cycle/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "OpenCycleMap" }
); 
var Transport = L.tileLayer(
  'https://tile.thunderforest.com/transport/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "Transport" }
); 
var Landscape = L.tileLayer(
  'https://tile.thunderforest.com/landscape/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "Landscape" }
); 
var Outdoors = L.tileLayer(
  'https://tile.thunderforest.com/outdoors/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "Outdoors" }
); 
var SpinalMap = L.tileLayer(
  'https://tile.thunderforest.com/spinal-map/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "SpinalMap" }
); 
var TransportDark = L.tileLayer(
  'https://tile.thunderforest.com/transport-dark/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "TransportDark" }
); 
var Pioneer = L.tileLayer(
  'https://tile.thunderforest.com/pioneer/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "Pioneer" }
); 
var MobileAtlas = L.tileLayer(
  'https://tile.thunderforest.com/mobile-atlas/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "MobileAtlas" }
); 
var Neighbourhood = L.tileLayer(
  'https://tile.thunderforest.com/neighbourhood/{z}/{x}/{y}.png?apikey=17dc0c0df61f47d4b13d3520ec5b1557',
  { maxZoom: 19, attribution: '© OpenStreetMap contributors', name: "Neighbourhood" }
); 




const $ = id => document.getElementById(id);
// Listen before adding the tiles, including when imagery is already cached.
let startupFinished = false;
let startupTimer;
function finishMapStartup() {
  if (startupFinished) return;
  startupFinished = true;
  clearTimeout(startupTimer);
  Esrimap.off('load', finishMapStartup);
  requestAnimationFrame(() => {
    $('map').classList.add('map-ready');
    $('map').setAttribute('aria-busy', 'false');
    $('mapStartup').hidden = true;
  });
}
Esrimap.on('load', finishMapStartup);
const map = L.map('map', { center: [58, -96], zoom: 4, layers: [Esrimap], zoomControl: false });
// Recheck after layout and whenever the container changes, including browser
// restoration and mobile viewport changes that do not fire a window resize.
let mapSizeFrame;
function syncMapSize() {
  cancelAnimationFrame(mapSizeFrame);
  mapSizeFrame = requestAnimationFrame(() => {
    map.invalidateSize({ pan: false, debounceMoveend: true });
  });
}
const mapSizeObserver = new ResizeObserver(syncMapSize);
mapSizeObserver.observe($('map'));
window.addEventListener('load', syncMapSize);
window.addEventListener('pageshow', syncMapSize);
syncMapSize();
// A slow tile service must not leave the map hidden indefinitely.
startupTimer = setTimeout(finishMapStartup, 4000);
L.control.zoom({ position: 'topright' }).addTo(map);
L.control.layers({
  'Satellite': Esrimap, 'OpenStreetMap': OpenStreetMap_Mapnik,
  'Cycle': OpenCycleMap, 'Transport': Transport, 'Landscape': Landscape,
  'Outdoors': Outdoors, 'Spinal': SpinalMap, 'Transport dark': TransportDark,
  'Pioneer': Pioneer, 'Mobile atlas': MobileAtlas, 'Neighbourhood': Neighbourhood,
}, null, { position: 'topright', collapsed: true }).addTo(map);
L.control.scale({ position: 'bottomright', imperial: false }).addTo(map);

let resultsLayer = null;
let boundaryLayer = null;
let polygonDocument = null;
let busy = false;
let watershedMap = null;
let watershedLayer = null;
let watershedLoading = false;

function setPanelOpen(open) {
  $('filterPanel').hidden = !open;
  $('filterToggle').setAttribute('aria-expanded', String(open));
  if (!open && $('filterPanel').contains(document.activeElement)) $('filterToggle').focus();
  map.invalidateSize();
}
$('filterToggle').addEventListener('click', () => setPanelOpen($('filterPanel').hidden));
$('collapseFilters').addEventListener('click', () => setPanelOpen(false));

for (const dialog of document.querySelectorAll('dialog')) {
  dialog.querySelector('[data-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
}
$('aboutButton').addEventListener('click', () => $('aboutDialog').showModal());
$('saveButton').addEventListener('click', () => {
  if (busy) return;
  $('downloadStatus').textContent = '';
  $('downloadError').hidden = true;
  $('downloadDialog').showModal();
});

function showError(message, target = 'errorMessage') {
  $(target).textContent = message;
  $(target).hidden = false;
}
function setBusy(active, message = 'Loading fires…') {
  busy = active;
  $('loadingMessage').hidden = !active;
  $('loadingText').textContent = message;
  $('filterPanel').setAttribute('aria-busy', String(active));
  for (const id of ['filterButton', 'saveButton', 'downloadButton', 'polygonFile', 'removePolygon', 'clearFilters']) $(id).disabled = active;
}
function collectFilters() {
  const fields = {
    min_year: 'minYear', max_year: 'maxYear', min_size: 'minSize', max_size: 'maxSize',
    distance_coords: 'distanceCoords', distance_radius: 'distanceRadius',
    watershed_name: 'watershedName', polygon_tol: 'polygonTol',
  };
  const filters = Object.fromEntries(Object.entries(fields).map(([key, id]) => [key, $(id).value.trim()]));
  filters.provinces = Array.from(document.querySelectorAll('#provincecheckboxes input:checked'), input => input.value);
  if (polygonDocument !== null) filters.polygon_geojson = polygonDocument;
  return filters;
}
async function postJSON(url, body) {
  const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `Request failed (${response.status}). Please try again.`;
    try { message = (await response.json()).error || message; } catch { /* Non-JSON server response. */ }
    throw new Error(message);
  }
  return response;
}
function popupDetails(properties) {
  const content = document.createElement('div');
  const heading = document.createElement('h3');
  heading.textContent = 'Fire details';
  content.appendChild(heading);
  for (const [label, key] of [['Year', 'fire_year'], ['Area (ha)', 'fire_size'], ['Source', 'data_source'], ['Acquisition', 'data_aquisition']]) {
    const row = document.createElement('div');
    row.textContent = `${label}: ${properties[key] ?? 'Unavailable'}`;
    content.appendChild(row);
  }
  return content;
}
async function loadFilteredData(event) {
  if (event) event.preventDefault();
  if (busy) return;
  $('errorMessage').hidden = true;
  setBusy(true);
  try {
    const response = await postJSON('/fx_main', collectFilters());
    const data = await response.json();
    // Build the replacement before removing existing results so failures preserve them.
    const layers = [L.geoJSON(data.fires, {
      style: { color: '#ed8956', weight: 1.5, fillColor: '#d8542c', fillOpacity: .42 },
      onEachFeature: (feature, layer) => layer.bindPopup(popupDetails(feature.properties || {})),
    })];
    if (data.user_buffer) layers.push(L.geoJSON(data.user_buffer, { style: { color: '#c4e8d5', weight: 2, fillOpacity: .08 } }));
    if (data.user_point) layers.push(L.geoJSON(data.user_point, {
      pointToLayer: (feature, latlng) => L.marker(latlng, { icon: L.divIcon({ className: 'point-marker', iconSize: [12, 12] }) }),
    }));
    if (data.watershed_polygon) layers.push(L.geoJSON(data.watershed_polygon, { style: { color: '#a7bbeb', weight: 2, fillOpacity: .07 } }));
    const replacement = L.layerGroup(layers).addTo(map);
    if (resultsLayer) map.removeLayer(resultsLayer);
    resultsLayer = replacement;
    if (boundaryLayer) boundaryLayer.bringToFront();
    const count = data.fires.features.length;
    $('foundMessage').textContent = `${count.toLocaleString()} ${count === 1 ? 'fire' : 'fires'} matched.`;
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}
$('filterForm').addEventListener('submit', loadFilteredData);

$('polygonFile').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file || busy) return;
  $('errorMessage').hidden = true;
  setBusy(true, 'Checking boundary…');
  try {
    if (!/\.(geojson|json)$/i.test(file.name)) throw new Error('Choose a .geojson or .json file.');
    if (file.size > 10 * 1024 * 1024) throw new Error('Boundary must be 10 MB or smaller.');
    let document;
    try { document = JSON.parse(await file.text()); } catch { throw new Error('Could not read the file. Choose valid GeoJSON.'); }
    const response = await postJSON('/validate_polygon', { polygon_geojson: document });
    const data = await response.json();
    const preview = L.geoJSON(data.geometry, { style: { color: '#72d5d9', weight: 2, fillOpacity: .06 }, interactive: false });
    const bounds = preview.getBounds();
    if (!bounds.isValid()) throw new Error('Boundary has no displayable geometry.');
    preview.addTo(map);
    if (boundaryLayer) map.removeLayer(boundaryLayer);
    boundaryLayer = preview;
    polygonDocument = document;
    $('polygonStatus').textContent = `${file.name} · ready to filter.`;
    $('removePolygon').hidden = false;
    map.fitBounds(bounds, { paddingTopLeft: [$('filterPanel').hidden ? 20 : Math.min(360, map.getSize().x / 2), 80], paddingBottomRight: [35, 35], maxZoom: 12 });
  } catch (error) {
    showError(error.message + (polygonDocument ? ' Previous boundary kept.' : ''));
  } finally {
    // Allow choosing the same file again, including after correcting it.
    $('polygonFile').value = '';
    setBusy(false);
  }
});
function removePolygon() {
  if (boundaryLayer) map.removeLayer(boundaryLayer);
  boundaryLayer = null;
  polygonDocument = null;
  $('polygonFile').value = '';
  $('polygonStatus').textContent = 'No boundary selected.';
  $('removePolygon').hidden = true;
}
$('removePolygon').addEventListener('click', () => {
  if (!busy) { removePolygon(); $('errorMessage').hidden = true; }
});
$('clearFilters').addEventListener('click', () => {
  if (busy) return;
  $('filterForm').reset();
  removePolygon();
  $('downloadFormat').value = 'csv';
  $('errorMessage').hidden = true;
  if (resultsLayer) map.removeLayer(resultsLayer);
  resultsLayer = null;
  $('foundMessage').textContent = 'Set filters to explore fires.';
});
$('provincecheckboxes').addEventListener('change', event => {
  const all = $('ALLcheckbox');
  const provinces = Array.from(document.querySelectorAll('#provincecheckboxes input:not(#ALLcheckbox)'));
  if (event.target === all && all.checked) provinces.forEach(input => { input.checked = false; });
  else if (event.target.checked) all.checked = false;
  if (!provinces.some(input => input.checked)) all.checked = true;
});

$('downloadButton').addEventListener('click', async () => {
  if (busy || !$('filterForm').reportValidity()) return;
  $('downloadError').hidden = true;
  $('errorMessage').hidden = true;
  $('downloadStatus').textContent = 'Preparing your download…';
  setBusy(true, 'Preparing download…');
  try {
    const format = $('downloadFormat').value;
    const response = await postJSON('/fx_main', { ...collectFilters(), download: 1, downloadFormat: format });
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const filename = match ? match[1] : `firecan_filtered_data.${format === 'json' ? 'geojson' : format}`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $('downloadStatus').textContent = 'Download ready.';
  } catch (error) {
    $('downloadStatus').textContent = '';
    showError(error.message, 'downloadError');
    showError(error.message);
  } finally {
    setBusy(false);
  }
});

$('watershedExplorerButton').addEventListener('click', async () => {
  $('watershedDialog').showModal();
  if (watershedLayer) {
    requestAnimationFrame(() => watershedMap.invalidateSize());
    return;
  }
  if (watershedLoading) return;
  watershedLoading = true;
  $('watershedStatus').textContent = 'Loading watershed boundaries…';
  try {
    const response = await fetch('/static/watershed_data.geojson');
    if (!response.ok) throw new Error('Could not load watershed boundaries. Try again.');
    const data = await response.json();
    if (!watershedMap) {
      watershedMap = L.map('watershedMap', { center: [52.5, -69.8], zoom: 5 });
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, attribution: 'Tiles © Esri' }).addTo(watershedMap);
    }
    watershedLayer = L.geoJSON(data, {
      style: { color: '#a7bbeb', weight: 1, fillOpacity: .12 },
      onEachFeature: (feature, layer) => {
        const content = document.createElement('div');
        const name = feature.properties?.watershed_name || '';
        const heading = document.createElement('h3');
        heading.textContent = name;
        const button = document.createElement('button');
        button.textContent = 'Use watershed';
        button.type = 'button';
        button.addEventListener('click', () => {
          $('watershedName').value = name;
          $('watershedDialog').close();
          setPanelOpen(true);
          $('watershedName').focus();
        });
        content.append(heading, button);
        layer.bindPopup(content);
      },
    }).addTo(watershedMap);
    watershedMap.invalidateSize();
    watershedMap.fitBounds(watershedLayer.getBounds());
    $('watershedStatus').textContent = '';
  } catch (error) {
    $('watershedStatus').textContent = error.message;
  } finally {
    watershedLoading = false;
  }
});
map.on('click', event => {
  const content = document.createElement('div');
  content.textContent = `${event.latlng.lat.toFixed(6)}, ${event.latlng.lng.toFixed(6)}`;
  L.popup().setLatLng(event.latlng).setContent(content).openOn(map);
});
