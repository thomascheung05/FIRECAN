MAX_SIZE_MB = 100
LOCAL_PORT = 5050
DOWNLOAD_FROM_GIT = True       # True: try the prebuilt data on Git first (falls back to the source if that fails). False: always download and process from the source


from firecan_fx import (
    download_processed_data, fx_process_watershed_data,
    create_processeddata_folder, convert_m_4326deg, timenow, create_data_folder,
    fx_filter_fires_data, fx_get_fire_data, fx_download_json, fx_download_csv, fx_download_gpkg,
    filter_number, parse_polygon_geojson, POLYGON_MAX_BYTES, TOTALFIRE_DATA_PATH, FIRE_DISPLAY_TOLERANCE_M,
    fx_fire_files_ready, fx_load_fire_display, fx_with_full_geometry,
)
from flask import Flask, request, jsonify # type: ignore
import json
import geopandas as gpd
import webbrowser
import threading
from pathlib import Path
import requests
import io
from shapely.geometry import mapping
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge


work_dir = Path(__file__).resolve().parent.parent
DATA_FOLDER_PATH = work_dir / 'data'
PROCESSED_DATA_FOLDER_PATH = DATA_FOLDER_PATH / "processed_data"
WATERSHED_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'watershed_data.parquet'
WATERSHED_PROCESSED_DATA_JSON_PATH = work_dir/ 'static' / 'watershed_data.geojson'





print('..',timenow(),'Starting watershed data pre-loading') # This section here loads in the watershed data, fire data is loaded per request

create_data_folder()
create_processeddata_folder()

# Fire data is downloaded/processed in the background when the app starts (see prepare_fire_data) so the page can open and show progress meanwhile
# Only the simplified copy of the fires is kept in memory, full detail geometry is read from disk for just the fires that need it
fire_data_status = {"state": "checking"}           # checking -> ready, or checking -> downloading -> ready / error
gdf_fires = None


def prepare_fire_data():
    global gdf_fires
    try:
        if not fx_fire_files_ready():
            fire_data_status["state"] = "downloading"
            fx_get_fire_data(DOWNLOAD_FROM_GIT)
        print(f'...... {timenow()} Loading in the Simplified Fire Data')
        gdf_fires = fx_load_fire_display()
        fire_data_status["state"] = "ready"
        print(f'...... {timenow()} Fire Data Ready')
    except Exception as exc:
        print(f'...... {timenow()} Could Not Get Fire Data: {exc}')
        fire_data_status["state"] = "error"


def start_fire_data_loading():
    # Called once per serving process: by __main__ for the dev server, by gunicorn.conf.py's post_fork hook for each Gunicorn worker
    threading.Thread(target=prepare_fire_data, daemon=True).start()


if WATERSHED_PROCESSED_DATA_PATH.exists() and WATERSHED_PROCESSED_DATA_JSON_PATH.exists():
    print(f'...... {timenow()} Loading in Watershed Data')
    gdf_watershed_data = gpd.read_parquet(WATERSHED_PROCESSED_DATA_PATH)
else:
    downloaded = False
    if DOWNLOAD_FROM_GIT:
        print(f'...... {timenow()} Attempting to Download Watershed Data from Git')
        downloaded = download_processed_data('https://github.com/thomascheung05/FIRECAN/releases/download/DataV1/watershed_data.parquet', 'watershed_data.parquet', PROCESSED_DATA_FOLDER_PATH)
        if downloaded:
            try:
                print(f'......... {timenow()} Download Sucess, Loading in Dataset')
                gdf_watershed_data = gpd.read_parquet(WATERSHED_PROCESSED_DATA_PATH)
            except Exception:
                downloaded = False
                WATERSHED_PROCESSED_DATA_PATH.unlink(missing_ok=True)
        if not downloaded:
            print(f'...... {timenow()} Could Not Get Watershed Data from Git, Falling Back to the Source')
    if downloaded:
        watershed_data_togeojson=gdf_watershed_data.copy()
        watershed_data_togeojson["geometry"] = watershed_data_togeojson["geometry"].simplify(tolerance=0.01)            # Simplyfying the tolerance for the geojson watershed polygons to reduce server load 
        watershed_data_togeojson.to_file(WATERSHED_PROCESSED_DATA_JSON_PATH, driver="GeoJSON")  #####
    else:
        print(f'...... {timenow()} The Raw Watershed Does Not Exist, Downloading Now')
        Watershed_data_url = ("https://services.arcgis.com/As5CFN3ThbQpy8Ph/arcgis/rest/services/1Watersheds/FeatureServer/0/query"
                              "?outFields=*&where=1%3D1&f=geojson&outSR=4326")
        response = requests.get(Watershed_data_url, timeout=120)
        response.raise_for_status()
        watershed_data = gpd.read_file(io.BytesIO(response.content))
        print(f'............ {timenow()} Pre-Processing the QC Watershed Data')   
        gdf_watershed_data = fx_process_watershed_data(watershed_data)
        print(f'............ {timenow()} Pre-Processing Complete')  

      
print(timenow(),'.. Data pre-loading complete. The app is now ready to serve requests')



app = Flask(__name__, static_folder=str(work_dir / 'static'))                                                     # This starts FLASK which allows me to talk back and forth with my web page and my java script
# Allow the boundary plus a small amount of JSON filter metadata.
app.config["MAX_CONTENT_LENGTH"] = POLYGON_MAX_BYTES + 64 * 1024


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(error):
    return jsonify(error="Boundary upload must be 10 MB or smaller."), 413


@app.route('/validate_polygon', methods=['POST'])
def validate_polygon():
    """Validate a boundary for preview without running a fire query."""
    try:
        if not request.is_json:
            raise ValueError("Send the boundary as a JSON object.")
        params = request.get_json()
        if not isinstance(params, dict):
            raise ValueError("Send the boundary as a JSON object.")
        boundary = parse_polygon_geojson(params.get("polygon_geojson"))
        return jsonify(geometry=mapping(boundary))
    except (ValueError, TypeError, BadRequest) as exc:
        return jsonify(error=str(exc) if not isinstance(exc, BadRequest) else "Could not read the JSON request."), 400


@app.route('/fx_main', methods=['GET', 'POST'])
def fx_main():
    try:
        if request.method == "POST":
            if not request.is_json:
                raise ValueError("Send filters as a JSON object.")
            params = request.get_json()
            if not isinstance(params, dict):
                raise ValueError("Send filters as a JSON object.")
            selected_provinces = params.get("provinces", ["ALL"])
        else:
            params = request.args
            selected_provinces = json.loads(params.get("provinces", '["ALL"]'))

        download = params.get("download", "0") in ("1", 1, True)
        download_format = params.get("downloadFormat", "csv")
        if download and download_format not in ("json", "csv", "gpkg"):
            raise ValueError("Choose CSV, GeoJSON, or GPKG for download.")
        tolerance = filter_number(params.get("polygon_tol"), "Polygon tolerance")
        if tolerance is None:
            tolerance = 50
        if fire_data_status["state"] == "error":
            return jsonify(error="Could not download or process the fire data. Check the server log and restart the app."), 503
        if fire_data_status["state"] != "ready":
            return jsonify(error="The fire data is still downloading. Try again once it's ready."), 503
        results = fx_filter_fires_data(
            gdf_fires, gdf_watershed_data, selected_provinces,
            **{key: params.get(key) for key in (
                "min_year", "max_year", "min_size", "max_size",
                "distance_coords", "distance_radius", "watershed_name",
            )},
            polygon_geojson=params.get("polygon_geojson"),
            geometry_source=TOTALFIRE_DATA_PATH,
        )
    except (ValueError, TypeError, BadRequest) as exc:
        return jsonify(error=str(exc) if not isinstance(exc, BadRequest) else "Could not read the JSON request."), 400

    filtered_data = results["filtered_gdf"]                # geometry is the in memory copy, simplified to FIRE_DISPLAY_TOLERANCE_M
    if download:
        if download_format == "csv":
            return fx_download_csv(filtered_data)            # no geometry in the CSV, no need to read it
        filtered_data = fx_with_full_geometry(filtered_data, TOTALFIRE_DATA_PATH)    # exports keep the original fire boundaries
        if download_format == "json":
            return fx_download_json(filtered_data, MAX_SIZE_MB)
        return fx_download_gpkg(filtered_data, MAX_SIZE_MB)

    # Display simplification must never change the shared dataset or exports.
    if tolerance < FIRE_DISPLAY_TOLERANCE_M:
        filtered_data = fx_with_full_geometry(filtered_data, TOTALFIRE_DATA_PATH)    # finer than the in memory copy, start from full detail
    display_data = filtered_data.to_crs("EPSG:4326").copy()
    if tolerance != FIRE_DISPLAY_TOLERANCE_M:
        display_data["geometry"] = display_data.geometry.simplify(
            tolerance=convert_m_4326deg(tolerance, 45), preserve_topology=True,
        )
    watershed_polygon = results["watershed_polygon"]
    combined_geojson = {
        "fires": json.loads(display_data.to_json()),
        "user_point": json.loads(results["user_point"].to_json()) if results["user_point"] is not None else None,
        "user_buffer": json.loads(results["buffer_geom"].to_json()) if results["buffer_geom"] is not None else None,
        "watershed_polygon": json.loads(gpd.GeoSeries(
            [watershed_polygon], crs=gdf_watershed_data.crs,
        ).to_crs("EPSG:4326").to_json()) if watershed_polygon is not None else None,
    }
    size = len(json.dumps(combined_geojson).encode("utf-8"))
    if size > MAX_SIZE_MB * 1024 * 1024:
        return jsonify(error=f"Data too large to load ({size / 1024 / 1024:.2f} MB). Narrow your filters or increase display tolerance."), 413
    return jsonify(combined_geojson)


@app.route('/data_status')
def data_status():
    return jsonify(state=fire_data_status["state"])


@app.route('/')
def serve_html():
    return app.send_static_file('firecan_web.html')

def open_browser():
    webbrowser.open_new(f"http://127.0.0.1:{LOCAL_PORT}")

if __name__ == '__main__':
    start_fire_data_loading()
    threading.Timer(1, open_browser).start()  # small delay so server is up first
    app.run(host="127.0.0.1", port=LOCAL_PORT)



