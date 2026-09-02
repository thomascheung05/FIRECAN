MAX_SIZE_MB = 100


from firecan_fx import fx_get_can_fire_data,convert_m_4326deg,fx_merge_provincial_fires,timenow,create_data_folder,fx_get_qc_fire_data,fx_filter_fires_data,fx_download_json,fx_download_csv,timenow, fx_download_gpkg, fx_get_qc_watershed_data
from flask import Flask, request # type: ignore
import json
import sys
import geopandas as gpd
import webbrowser
import threading

create_data_folder()

print('------------------------Starting data pre-loading. This may take a few minutes...', timenow(),'------------------------')                                      # This section here loads in the data, it uses the scrap donne quebec function and the process qc fire data fuction

gdf_can_fires = fx_get_can_fire_data()
gdf_qc_fires = fx_get_qc_fire_data()
gdf_qc_watershed_data = fx_get_qc_watershed_data()
gdf_fires = fx_merge_provincial_fires(gdf_qc_fires, gdf_can_fires)

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



