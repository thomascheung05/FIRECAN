MAX_SIZE_MB = 100


from firecan_fx import get_work_dir, download_processed_data,fx_process_watershed_data,fx_process_qcfire_data,create_processeddata_folder,fx_process_canfire_data, fx_download_raw_data,convert_m_4326deg,fx_merge_provincial_fires,timenow,create_data_folder,fx_filter_fires_data,fx_download_json,fx_download_csv,timenow, fx_download_gpkg
from flask import Flask, request # type: ignore
import json
import geopandas as gpd
import webbrowser
import threading
from pathlib import Path



work_dir = get_work_dir()
DATA_FOLDER_PATH = work_dir / 'data'
PROCESSED_DATA_FOLDER_PATH = work_dir / "data" / "processed_data"
CAN_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / "can_processed_fire_data.parquet"  # processed data output
CAN_RAW_DATA_FOLDER_PATH = work_dir / "data" / "canfire"
CAN_RAW_DATA_PATH = work_dir / "data" / "canfire" / "NFDB_poly_1972to2020_20250630.shp"
QC_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'qc_processed_fire_data.parquet'
QC_BEFORE_RAW_DATA_FOLDER_PATH = DATA_FOLDER_PATH / 'qcfires_before76' 
QC_AFTER_RAW_DATA_FOLDER_PATH = DATA_FOLDER_PATH / 'qcfires_after76' 
QC_BEFORE_RAW_DATA_PATH = QC_BEFORE_RAW_DATA_FOLDER_PATH / 'FEUX_ANCIENS_PROV.gpkg'
QC_AFTER_RAW_DATA_PATH = QC_AFTER_RAW_DATA_FOLDER_PATH / 'FEUX_PROV.gpkg'
WATERSHED_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'qc_watershed_data.parquet'
WATERSHED_PROCESSED_DATA_JSON_PATH = work_dir/ 'static' / 'qc_watershed_data.geojson'
WATERSHED_RAW_DATA_FOLDER_PATH = work_dir / "data" / 'qcwatershed_data' 
WATERSHED_RAW_DATA_PATH = WATERSHED_RAW_DATA_FOLDER_PATH / 'CE_bassin_multi.gdb'
TOTALFIRE_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'TotalFire_data.parquet'





print('------------------------Starting data pre-loading. This may take a few minutes...', timenow(),'------------------------')                                      # This section here loads in the data, it uses the scrap donne quebec function and the process qc fire data fuction

create_data_folder()
create_processeddata_folder()

if TOTALFIRE_DATA_PATH.exists():
    print(f'...... {timenow()} The Full Dataset Already Exists, Loading in Now')
    gdf_fires = gpd.read_parquet(TOTALFIRE_DATA_PATH)
else: 
    print(f'...... {timenow()} Downloading Fire Data from Git')
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



if WATERSHED_PROCESSED_DATA_PATH.exists():
    print(f'...... {timenow()} Loading in Watershed Data')
    gdf_qc_watershed_data = gpd.read_parquet(WATERSHED_PROCESSED_DATA_PATH)
else:
    print(f'...... {timenow()} Downloading Watershed Data from Git')
    downloaded = download_processed_data('https://github.com/thomascheung05/FIRECAN/releases/download/DataV1/qc_watershed_data.parquet', 'qc_watershed_data.parquet', PROCESSED_DATA_FOLDER_PATH)
    if downloaded:
        (f'......... {timenow()} Download Sucess, Loading in Dataset')
        gdf_qc_watershed_data = gpd.read_parquet(WATERSHED_PROCESSED_DATA_PATH)
    else:
        print(f'...... {timenow()} The Raw Quebec Watershed Does Not Exist, Downloading Now')
        fx_download_raw_data(
            'qcwatershed_data',
            'https://stqc380donopppdtce01.blob.core.windows.net/donnees-ouvertes/Bassins_hydrographiques_multi_echelles/CE_bassin_multi.gdb.zip',
            'CE_bassin_multi.gdb.zip',
            )  
        print(f'............ {timenow()} Pre-Processing the QC Watershed Data')   
        gdf_qc_watershed_data = fx_process_watershed_data()
        print(f'............ {timenow()} Pre-Processing Complete')  

      
print('---------------Data pre-loading complete. The app is now ready to serve requests.', timenow(),'------------------------')



app = Flask(__name__, static_folder='static')                                                      # This starts FLASK which allows me to talk back and forth with my web page and my java script
@app.route('/fx_main', methods=['GET'])
def fx_main():                                                                                    # This is the main fuctino that is run when my python is called by Flask 
    #################### ######################################## ######################################## ######################################## ####################
    # FLASK main function 
    #################### ######################################## ######################################## ######################################## ####################
    min_year = request.args.get('min_year', None)                                                    # This section here assings varibales for all the user inputed filtering conditions
    max_year = request.args.get('max_year', None)                                     
    min_size = request.args.get('min_size', None)
    max_size = request.args.get('max_size', None)
    distance_coords = request.args.get('distance_coords', None)
    distance_radius = request.args.get('distance_radius', None)
    watershed_name = request.args.get('watershed_name', None)
    is_download_requested = request.args.get('download', '0') == '1'                                      # Checks if we should be displaying data or downloading it
    downloadformat = request.args.get('downloadFormat', None)
    provinces_str = request.args.get('provinces', '[]')   
    selected_provinces = json.loads(provinces_str)         
    pc_name = request.args.get('pc_name', None)
    
    print(timenow(),'Filtering Data')                                                                                 # Uses the filtering fire function to return a dataset with only the fires the user wants 
    results= fx_filter_fires_data(
                                    gdf_fires,
                                    gdf_qc_watershed_data,
                                    selected_provinces,
                                    min_year=min_year,
                                    max_year=max_year,
                                    min_size=min_size,
                                    max_size=max_size,
                                    distance_coords=distance_coords,
                                    distance_radius=distance_radius,
                                    watershed_name=watershed_name,
                                    pc_name = pc_name
                                        )
    print(timenow(),'Done Filtering Data')

    filtered_data = results["filtered_gdf"]
    watershed_polygon = results["watershed_polygon"]
    userpoint = results["user_point"]
    bufferdeg = results["buffer_geom"]

        
    if is_download_requested:  
        #################### ######################################## ######################################## ######################################## ####################
        # Return a file to download
        #################### ######################################## ######################################## ######################################## ####################                                                                                               
        if downloadformat == 'json':
            return fx_download_json(filtered_data, MAX_SIZE_MB)
        elif downloadformat == 'csv':
            return fx_download_csv(filtered_data)
        elif downloadformat == 'gpkg':
            return fx_download_gpkg(filtered_data, MAX_SIZE_MB)
    else:   
        #################### ######################################## ######################################## ######################################## ####################                                                                                               
        # Return a dataset to be displayed
        #################### ######################################## ######################################## ######################################## ####################                                                                                                                                                                                                    
        print(timenow(),'Converting to geojson',filtered_data.shape)

        polygon_tol = request.args.get('polygon_tol', None)
        polygon_tol = float(polygon_tol)
        polygon_tol_deg = convert_m_4326deg(polygon_tol, 45)

        filtered_data["geometry"] = filtered_data["geometry"].simplify(tolerance=polygon_tol_deg, preserve_topology=True)         # add precision option to change how good the polygons look vs load time
        geojson_fires = json.loads(filtered_data.to_json())                                                                               
        print(timenow(),'Done Converting to geojson')    

        geojson_point = json.loads(userpoint.to_json()) if userpoint is not None else None
        geojson_buffer = json.loads(bufferdeg.to_json()) if bufferdeg is not None else None
        
        if watershed_polygon is not None:
            ws_gs = gpd.GeoSeries([watershed_polygon], crs=gdf_qc_watershed_data.crs)
            ws_gs = ws_gs.to_crs("EPSG:4326")
            geojson_watershedpolygon = json.loads(ws_gs.to_json())
        else:
            geojson_watershedpolygon = None

        combined_geojson = {
            "fires": geojson_fires,
            "user_point": geojson_point,
            "user_buffer": geojson_buffer,
            "watershed_polygon" : geojson_watershedpolygon
        }

        #################### ######################################## ######################################## ######################################## ####################                                                                                               
        # File size cap to reduce server cost
        #################### ######################################## ######################################## ######################################## ####################                                                                                                                                                                                                    
        MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
        geojson_bytes = len(json.dumps(combined_geojson).encode('utf-8'))
        print(f'File Size {geojson_bytes/1000000}')
        if geojson_bytes > MAX_SIZE_BYTES:                                                  # Error message
            print(f'{geojson_bytes/1000000} is too big')
            return {"error": f"Data too large to load ({geojson_bytes / 1024 / 1024:.2f} MB). Please re-fresh and narrow your filter."}, 413


        return json.dumps(combined_geojson)

                                
@app.route('/')
def serve_html():
    return app.send_static_file('firecan_web.html')

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")

if __name__ == '__main__':
    threading.Timer(1, open_browser).start()  # small delay so server is up first
    app.run(port=5000)



