"use strict";
const $ = id => document.getElementById(id);
let mainMap;
let polygonDocument = null;
let busy = false;
let watershedMap = null;
let watershedLayer = null;
let watershedLoading = false;

function setPanelOpen(open) {
  $('filterPanel').hidden = !open;
  $('filterToggle').setAttribute('aria-expanded', String(open));
  if (!open && $('filterPanel').contains(document.activeElement)) $('filterToggle').focus();
  FireMap.resize();
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
// Fire queries stay disabled until the server has the fire data on disk.
let fireDataReady = false;
function setBusy(active, message = 'Loading fires…') {
  busy = active;
  $('loadingMessage').hidden = !active;
  $('loadingText').textContent = message;
  $('filterPanel').setAttribute('aria-busy', String(active));
  for (const id of ['polygonFile', 'removePolygon']) $(id).disabled = active || !fireDataReady;
  $('clearFilters').disabled = !fireDataReady || (active && message !== 'Loading fires…');
  for (const id of ['filterButton', 'saveButton', 'downloadButton']) $(id).disabled = active || !fireDataReady;
}
let dataStatusTimer;
function showDataStatus(message, { spinner = false, error = false, dismissable = false } = {}) {
  clearTimeout(dataStatusTimer);
  $('dataStatusText').textContent = message;
  $('dataStatusSpinner').hidden = !spinner;
  $('dataStatusClose').hidden = !dismissable;
  $('dataStatus').classList.toggle('is-error', error);
  $('dataStatus').hidden = false;
}
$('dataStatusClose').addEventListener('click', () => { $('dataStatus').hidden = true; });
let mapManifest = null;
let queryController = null;
let queryGeneration = 0;
async function watchFireData() {
  try {
    const response = await fetch('/data_status');
    if (!response.ok) throw new Error('Could not check fire data readiness.');
    const { state } = await response.json();
    if (state === 'error') throw new Error('Could not prepare fire data. Check the terminal and restart the app.');
    if (state !== 'ready') {
      showDataStatus('Preparing fire data. The first download can take up to 15 minutes.', { spinner: true });
      setTimeout(watchFireData, 3000);
      return;
    }
    const metadataResponse = await fetch('/map_manifest', { cache: 'no-store' });
    const metadata = await metadataResponse.json();
    if (!metadataResponse.ok) throw new Error(metadata.error || 'Local fire tiles are unavailable.');
    mapManifest = metadata;
    await FireMap.loadArchive(metadata);
    fireDataReady = true;
    $('dataStatus').hidden = true;
    setBusy(false);
    await loadFilteredData();
  } catch (error) {
    showDataStatus(error.message, { error: true });
  }
}
setBusy(false);
function collectFilters() {
  const fields = {
    min_year: 'minYear', max_year: 'maxYear', min_size: 'minSize', max_size: 'maxSize',
    distance_coords: 'distanceCoords', distance_radius: 'distanceRadius',
    watershed_name: 'watershedName',
  };
  const filters = Object.fromEntries(Object.entries(fields).map(([key, id]) => [key, $(id).value.trim()]));
  filters.provinces = Array.from(document.querySelectorAll('#provincecheckboxes input:checked'), input => input.value);
  if (polygonDocument !== null) filters.polygon_geojson = polygonDocument;
  return filters;
}
async function postJSON(url, body, signal) {
  const response = await fetch(url, {
    signal, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
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
  if (!fireDataReady) return;
  queryController?.abort();
  const generation = ++queryGeneration;
  queryController = new AbortController();
  $('errorMessage').hidden = true;
  setBusy(true);
  try {
    const start = performance.now();
    const response = await postJSON('/map_query', { ...collectFilters(), dataset_version: mapManifest.dataset_version }, queryController.signal);
    const data = await response.json();
    if (generation !== queryGeneration) return;
    FireMap.apply(data);
    window.firecanLastQueryMs = performance.now() - start;
    $('foundMessage').textContent = data.count ? `${data.count.toLocaleString()} ${data.count === 1 ? 'fire' : 'fires'} matched.` : 'No fires match these filters.';
  } catch (error) {
    if (generation === queryGeneration && error.name !== 'AbortError') showError(error.message + ' Previous selection kept.');
  } finally {
    if (generation === queryGeneration) setBusy(false);
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
    FireMap.boundary(data.geometry);
    polygonDocument = document;
    $('polygonStatus').textContent = `${file.name} · ready to filter.`;
    $('removePolygon').hidden = false;
  } catch (error) {
    showError(error.message + (polygonDocument ? ' Previous boundary kept.' : ''));
  } finally {
    // Allow choosing the same file again, including after correcting it.
    $('polygonFile').value = '';
    setBusy(false);
  }
});
function removePolygon() {
  if (mapManifest) FireMap.boundary(null);
  polygonDocument = null;
  $('polygonFile').value = '';
  $('polygonStatus').textContent = 'No boundary selected.';
  $('removePolygon').hidden = true;
}
$('removePolygon').addEventListener('click', () => {
  if (!busy) { removePolygon(); $('errorMessage').hidden = true; }
});
$('clearFilters').addEventListener('click', () => {
  queryController?.abort();
  ++queryGeneration;
  $('filterForm').reset();
  removePolygon();
  $('downloadFormat').value = 'csv';
  $('errorMessage').hidden = true;
  FireMap.resetView();
  loadFilteredData();
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
try {
  mainMap = FireMap.initialize((features, coordinates) => {
    if (features.length) return popupDetails(features[0].properties || {});
    const content = document.createElement('div');
    content.textContent = `${coordinates.lat.toFixed(6)}, ${coordinates.lng.toFixed(6)}`;
    return content;
  }, message => showDataStatus(message, { error: true, dismissable: true }));
  const observer = new ResizeObserver(() => FireMap.resize());
  observer.observe($('map'));
  window.addEventListener('pageshow', () => FireMap.resize());
  watchFireData();
} catch (error) {
  $('mapStartup').hidden = true;
  $('map').setAttribute('aria-busy', 'false');
  showDataStatus(error.message, { error: true });
}
