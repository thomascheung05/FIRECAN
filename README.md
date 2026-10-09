# FIRECAN

FIRECAN is a web-based mapping application that enables users to filter and visualize historical forest fire data across Canada. It processes and serves fire data from Donnees Quebec and the Canadian Wildland Fire Information System (CWFIS), allowing for dynamic exploration on an interactive map.

The backend is built with Python using Flask and GeoPandas for data processing, while the frontend leverages Leaflet.js to render geographic data and provide an interactive user experience. 

## Features

*   **Interactive Map**: A full-window map with a collapsible floating filter panel and multiple base layers (e.g., Esri Imagery, OpenStreetMap).
*   **Comprehensive Filtering**:
    *   Filter fires by province or select all.
    *   Specify a date range (minimum/maximum year).
    *   Filter by fire size in hectares (min/max).
    *   Isolate fires within a specific radius of a coordinate point.
    *   Select fires contained within a specific Quebec watershed.
    *   Upload your own GeoJSON boundary to select fires that overlap or touch it.
*   **Performance Tuning**: Adjust the polygon tolerance to simplify geometries, reducing load times for large datasets.
*   **Data Export**: Download your filtered dataset in various formats, including GeoJSON, CSV, and GPKG.
*   **Watershed Explorer**: An interactive map tool to find and select Quebec watersheds for filtering.

## Getting Started

### Prerequisites

*   Python 3.x

### Installation

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/thomascheung05/firecan.git
    cd firecan
    ```

2.  **Run Firecan.sh**
    ```sh
    ./FIRECAN.sh
    ```


### First-Time Setup

The first time you run the application, it will automatically create a VENV, install the requirements and download the necessary fire and watershed data (approximately 2 GB). This process can take up to 15 minutes, with the majority of the time spent on the download. Once processed, the data is saved locally for faster startup on subsequent runs.


3.  **Using the Interface:**
    *   The app opens at **http://127.0.0.1:5050**. You can paste this address into Chrome or another browser.
    *   Use the floating Filters panel to set your desired filters. Collapse it to see more of the map.
    *   Click the **"Filter Map"** button to apply the filters and display the corresponding fire polygons on the map.
    *   Click **Export** to download the current filter selection as CSV, GeoJSON, or GeoPackage. Geometry exports keep the original fire boundaries.
    *   Open **About** for help and data-source links.

<!-- ==== [EFFICIENCY UPDATE] ==== -->
### Display data (one-time build)

After the fire dataset is available, FIRECAN builds two files from it once (about 5–10 minutes) and uses them from then on:

* `data/processed_data/TotalFire_display.parquet`: fire attributes plus boundaries pre-simplified for the map at 50 m, 250 m and 1 km. This is the only fire file loaded at startup.
* `data/processed_data/TotalFire_geometry.parquet`: the original, full-detail boundaries. Exports read only the rows they need from it.

The map uses the closest stored level at or below your display tolerance and simplifies further only when needed. Tolerances below 50 m read the original boundaries for the matching fires. Filters run on the 50 m boundaries, so a fire within about 50 m of a radius, watershed or uploaded boundary edge may be matched differently than with its full-detail outline. Exports always contain the original boundaries.

To rebuild, delete both files and restart. `TotalFire_data.parquet` is no longer read after the build and can be deleted to free about 2 GB; it is downloaded again if a rebuild needs it.
<!-- ==== [END EFFICIENCY UPDATE] ==== -->

## Configuration

### Result Size Limit

Large map results and geometry exports have a 100 MB response limit. To adjust this, you can change the `MAX_SIZE_MB` variable at the top of the `app/firecan_main.py` file.

```python
# firecan_main.py
MAX_SIZE_MB = 100 # Change this value as needed
```

## Data Sources

FIRECAN utilizes publicly available data from the following sources:

*   **Quebec Fires**: [Données Québec - Feux de forêt](https://www.donneesquebec.ca/recherche/dataset/feux-de-foret)
*   **Watersheds**: [Esri Canada Education and Research](https://hub.arcgis.com/maps/12b6e33d5a754c92b97ae5d0fed6940a/about)
*   **All Other Provinces**: [Canadian Wildland Fire Information System (CWFIS)](https://cwfis.cfs.nrcan.gc.ca/datamart)

## Project Structure

*   `app/firecan_main.py`: The main Flask application file that handles HTTP requests, serves the frontend, and orchestrates the data filtering and response generation.
*   `app/firecan_fx.py`: A collection of utility functions responsible for downloading, pre-processing, filtering, and formatting the geographic data.
*   `requirements.txt`: A list of Python dependencies required for the project.
*   `static/`: Directory containing all frontend assets.
    *   `firecan_web.html`: The single-page HTML structure for the application.
    *   `firecan_logic.js`: Core frontend JavaScript for handling user interactions, API calls to the backend, and map rendering with Leaflet.
    *   `firecan_style.css`: Custom CSS for styling the web application.
    *   `leaflet.js` & `leaflet.css`: The Leaflet library files for the interactive map.
  



## Uploading a boundary

Under **Your boundary**, choose a `.geojson` or `.json` file up to 10 MB. The file must use EPSG:4326 longitude/latitude coordinates, in `[longitude, latitude]` order. Polygon and MultiPolygon geometries are supported, directly or inside a Feature or FeatureCollection. Collections must contain only polygon features; all features act as one search area, preserving holes.

FIRECAN validates the boundary, previews it in cyan, and zooms to it. Click **Filter Map** to apply it. Matching includes fires that overlap or touch the boundary, combined with other active filters. It selects whole fire records rather than clipping their geometry or recalculating area. The same filters apply to exports.

Choose another file to replace the boundary, or click **Remove**. Invalid replacements keep the previous boundary. **Reset** clears the boundary and results and restores All provinces and the 50-metre display tolerance. Uploads remain temporary and are not saved on disk.

## API and focused checks

`GET /fx_main` remains supported. `POST /fx_main` accepts a JSON object with the same filter names (`min_year`, `max_year`, `min_size`, `max_size`, `distance_coords`, `distance_radius`, `watershed_name`, `polygon_tol`), a `provinces` array, and optional `polygon_geojson`. Omitted filters are inactive; omitted provinces select all and omitted tolerance defaults to 50 metres. Set `download` to `1` and `downloadFormat` to `csv`, `json`, or `gpkg` for an attachment.

`POST /validate_polygon` accepts `{ "polygon_geojson": ... }` and returns the combined validated `geometry` for preview, without querying fires. Invalid input returns HTTP 400 with an `error` message; oversized request bodies return HTTP 413. The frontend checks the source file's 10 MB limit before uploading; the API also limits polygon size and request size.

Run the compact filtering and export checks with:

```sh
venv/bin/python -m unittest discover -s tests -v
```

They use small synthetic datasets and do not load or download the historical fire dataset.
