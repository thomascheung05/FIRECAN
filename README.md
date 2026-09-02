# FIRECAN

FIRECAN is a web-based mapping application that enables users to filter and visualize historical forest fire data across Canada. It processes and serves fire data from Donnees Quebec and the Canadian Wildland Fire Information System (CWFIS), allowing for dynamic exploration on an interactive map.

The backend is built with Python using Flask and GeoPandas for data processing, while the frontend leverages Leaflet.js to render geographic data and provide an interactive user experience.

## Features

*   **Interactive Map**: Visualize fire perimeters on a dynamic map with multiple base layers (e.g., Esri Imagery, OpenStreetMap).
*   **Comprehensive Filtering**:
    *   Filter fires by province or select all.
    *   Specify a date range (minimum/maximum year).
    *   Filter by fire size in hectares (min/max).
    *   Isolate fires within a specific radius of a coordinate point.
    *   Select fires contained within a specific Quebec watershed.
    *   Filter fires by National Park.
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
    *   Use the sidebar to set your desired filters.
    *   Click the **"Filter Map"** button to apply the filters and display the corresponding fire polygons on the map.
    *   Click the **Save** icon to open the download modal and export the filtered data.

## Configuration

### Request Size Limit

When running locally, you may encounter request size limits for very large queries. To adjust this, you can change the `MAX_SIZE_MB` variable at the top of the `firecan_main.py` file.

```python
# firecan_main.py
MAX_SIZE_MB = 10 # Change this value as needed
```

## Data Sources

FIRECAN utilizes publicly available data from the following sources:

*   **Quebec Fires**: [Données Québec - Feux de forêt](https://www.donneesquebec.ca/recherche/dataset/feux-de-foret)
*   **Quebec Watersheds**: [Données Québec - Bassins hydrographiques](https://www.donneesquebec.ca/recherche/dataset/bassins-hydrographiques-multi-echelles-du-quebec)
*   **All Other Provinces**: [Canadian Wildland Fire Information System (CWFIS)](https://cwfis.cfs.nrcan.gc.ca/datamart)

## Project Structure

*   `firecan_main.py`: The main Flask application file that handles HTTP requests, serves the frontend, and orchestrates the data filtering and response generation.
*   `firecan_fx.py`: A collection of utility functions responsible for downloading, pre-processing, filtering, and formatting the geographic data.
*   `requirements.txt`: A list of Python dependencies required for the project.
*   `static/`: Directory containing all frontend assets.
    *   `firecan_web.html`: The single-page HTML structure for the application.
    *   `firecan_logic.js`: Core frontend JavaScript for handling user interactions, API calls to the backend, and map rendering with Leaflet.
    *   `firecan_style.css`: Custom CSS for styling the web application.
    *   `leaflet.js` & `leaflet.css`: The Leaflet library files for the interactive map.
