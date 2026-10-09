MAX_SIZE_MB = 100
LOCAL_PORT = 5050


from firecan_fx import (
    download_processed_data, fx_process_watershed_data, fx_process_qcfire_data,
    create_processeddata_folder, fx_process_canfire_data, fx_download_raw_data,
    convert_m_4326deg, fx_merge_provincial_fires, timenow, create_data_folder,
    fx_filter_fires_data, fx_download_json, fx_download_csv, fx_download_gpkg,
    filter_number, parse_polygon_geojson, POLYGON_MAX_BYTES,
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
CAN_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / "can_processed_fire_data.parquet"  # processed data output
CAN_RAW_DATA_FOLDER_PATH = DATA_FOLDER_PATH / "canfire"
CAN_RAW_DATA_PATH = DATA_FOLDER_PATH / "canfire" / "NFDB_poly_1972to2020_20250630.shp"
QC_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'qc_processed_fire_data.parquet'
QC_BEFORE_RAW_DATA_FOLDER_PATH = DATA_FOLDER_PATH / 'qcfires_before76' 
QC_AFTER_RAW_DATA_FOLDER_PATH = DATA_FOLDER_PATH / 'qcfires_after76' 
QC_BEFORE_RAW_DATA_PATH = QC_BEFORE_RAW_DATA_FOLDER_PATH / 'FEUX_ANCIENS_PROV.gpkg'
QC_AFTER_RAW_DATA_PATH = QC_AFTER_RAW_DATA_FOLDER_PATH / 'FEUX_PROV.gpkg'
WATERSHED_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'watershed_data.parquet'
WATERSHED_PROCESSED_DATA_JSON_PATH = work_dir/ 'static' / 'watershed_data.geojson'
TOTALFIRE_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'TotalFire_data.parquet'





print('------------------------Starting data pre-loading. This may take a few minutes...', timenow(),'------------------------')                                      # This section here loads in the data, it uses the scrap donne quebec function and the process qc fire data fuction

create_data_folder()
create_processeddata_folder()

if TOTALFIRE_DATA_PATH.exists():
    print(f'...... {timenow()} The Full Dataset Already Exists, Loading in Now')
    gdf_fires = gpd.read_parquet(TOTALFIRE_DATA_PATH)
else: 
    print(f'...... {timenow()} Attempting to Download Fire Data from Git')
    downloaded = download_processed_data('https://github.com/thomascheung05/FIRECAN/releases/download/DataV1/TotalFire_data.parquet', 'TotalFire_data.parquet', PROCESSED_DATA_FOLDER_PATH)
    if downloaded:
        (f'......... {timenow()} Download Sucess, Loading in Dataset')
        gdf_fires = gpd.read_parquet(TOTALFIRE_DATA_PATH)
    else:
        if not CAN_PROCESSED_DATA_PATH.exists():
            print(f'...... {timenow()} The Raw Canada Data Does Not Exist, Downloading Now')
            fx_download_raw_data('canfire','https://cwfis.cfs.nrcan.gc.ca/downloads/nfdb/fire_poly/current_version/NFDB_poly.zip','NFDB_poly.zip',)    
            print(f'............ {timenow()} Pre-Processing the Canada Data')  
            gdf_can_fires = fx_process_canfire_data()
            print(f'............ {timenow()} Pre-Processing Complete')  
        else:
            gdf_can_fires = gpd.read_parquet(CAN_PROCESSED_DATA_PATH)

        if not QC_PROCESSED_DATA_PATH.exists():
            print(f'...... {timenow()} The Raw Quebec Data Does Not Exist, Downloading Now (This May Take Up to 20 Minutes)')
            if not QC_AFTER_RAW_DATA_PATH.exists():
                fx_download_raw_data('qcfires_after76','https://diffusion.mffp.gouv.qc.ca/Diffusion/DonneeGratuite/Foret/PERTURBATIONS_NATURELLES/Feux_foret/02-Donnees/PROV/FEUX_PROV_GPKG.zip','FEUX_PROV_GPKG.zip')
            if not QC_BEFORE_RAW_DATA_PATH.exists():
                fx_download_raw_data('qcfires_before76','https://diffusion.mffp.gouv.qc.ca/Diffusion/DonneeGratuite/Foret/PERTURBATIONS_NATURELLES/Feux_foret/02-Donnees/PROV/FEUX_ANCIENS_PROV_GPKG.zip','FEUX_PROV_GPKG.zip')
            print(f'............ {timenow()} Pre-Processing the QC Data')     
            gdf_qc_fires = fx_process_qcfire_data()
            print(f'............ {timenow()} Pre-Processing Complete')  
        else:
            gdf_qc_fires = gpd.read_parquet(QC_PROCESSED_DATA_PATH)
        print(f'.................. {timenow()} Merging All Fire Data and Saving For Later Use')   
        gdf_fires = fx_merge_provincial_fires(gdf_qc_fires, gdf_can_fires)



if WATERSHED_PROCESSED_DATA_PATH.exists() and WATERSHED_PROCESSED_DATA_JSON_PATH.exists():
    print(f'...... {timenow()} Loading in Watershed Data')
    gdf_watershed_data = gpd.read_parquet(WATERSHED_PROCESSED_DATA_PATH)
else:
    print(f'...... {timenow()} Attempting to Download Watershed Data from Git')
    downloaded = download_processed_data('https://github.com/thomascheung05/FIRECAN/releases/download/DataV1/watershed_data.parquet', 'watershed_data.parquet', PROCESSED_DATA_FOLDER_PATH)
    if downloaded:
        (f'......... {timenow()} Download Sucess, Loading in Dataset')
        gdf_watershed_data = gpd.read_parquet(WATERSHED_PROCESSED_DATA_PATH)
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

      
print('---------------Data pre-loading complete. The app is now ready to serve requests.', timenow(),'------------------------')



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
        results = fx_filter_fires_data(
            gdf_fires, gdf_watershed_data, selected_provinces,
            **{key: params.get(key) for key in (
                "min_year", "max_year", "min_size", "max_size",
                "distance_coords", "distance_radius", "watershed_name",
            )},
            polygon_geojson=params.get("polygon_geojson"),
        )
    except (ValueError, TypeError, BadRequest) as exc:
        return jsonify(error=str(exc) if not isinstance(exc, BadRequest) else "Could not read the JSON request."), 400

    filtered_data = results["filtered_gdf"]
    if download:
        if download_format == "json":
            return fx_download_json(filtered_data, MAX_SIZE_MB)
        if download_format == "csv":
            return fx_download_csv(filtered_data)
        return fx_download_gpkg(filtered_data, MAX_SIZE_MB)

    # Display simplification must never change the shared dataset or exports.
    display_data = filtered_data.to_crs("EPSG:4326").copy()
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


@app.route('/')
def serve_html():
    return app.send_static_file('firecan_web.html')

def open_browser():
    webbrowser.open_new(f"http://127.0.0.1:{LOCAL_PORT}")

if __name__ == '__main__':
    threading.Timer(1, open_browser).start()  # small delay so server is up first
    app.run(host="127.0.0.1", port=LOCAL_PORT)



