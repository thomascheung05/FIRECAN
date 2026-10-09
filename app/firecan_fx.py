import zipfile
import json
import requests
import geopandas as gpd
from datetime import datetime
from flask import send_file   # type: ignore
import io
from pathlib import Path
import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import unary_union
import math
import shutil



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



def timenow():
    return datetime.now().strftime('%H:%M:%S')





def repojectdata(data, targetcrs):
    #################### ######################################## ######################################## ######################################## ####################
    # Reprojects data to target crs 
    #################### ######################################## ######################################## ######################################## ####################

    is_targercrs = data.crs.to_epsg() == targetcrs

    if is_targercrs:
        print(f'............ The data is already in {targetcrs}')
        return data
    else:
        data = data.to_crs(targetcrs)    
        return data





def create_data_folder():
    #################### ######################################## ######################################## ######################################## ####################
    # Creates the data folder in directory if not there 
    #################### ######################################## ######################################## ######################################## ####################    
    if not DATA_FOLDER_PATH.exists(): 
        DATA_FOLDER_PATH.mkdir(parents=True, exist_ok=True)
        print('Data Folder Created')

def create_processeddata_folder():
    #################### ######################################## ######################################## ######################################## ####################
    # Creates the data folder in directory if not there 
    #################### ######################################## ######################################## ######################################## ####################    
    if not PROCESSED_DATA_FOLDER_PATH.exists(): 
        PROCESSED_DATA_FOLDER_PATH.mkdir(parents=True, exist_ok=True)
        print('Processed Data Folder Created')



def convert_m_4326deg(meters, lat):
    #################### ######################################## ######################################## ######################################## ####################
    # Used to convert meters to lat and lon deg for polygon tolerance (it inputs a distance value in lat long deg)
    #################### ######################################## ######################################## ######################################## ####################
    deg_lat = meters / 111320.0
    deg_lon = meters / (111320.0 * math.cos(math.radians(lat)))

    larger = max(deg_lat, deg_lon)
    return larger



def fx_download_raw_data(dataname, url, zipname):        
    #################### ######################################## ######################################## ######################################## ####################
    # downloads raw data using a URL and unpacks the zip 
    #################### ######################################## ######################################## ######################################## ####################    
      
    savefolder = work_dir / "data" / dataname
    zip_path = savefolder / zipname                                                                # Name of zip file depends on the data being dowloaded, for fire data its the same but not for watershed data
                                                        
    savefolder.mkdir(parents=True, exist_ok=True)
    response = requests.get(url)                                                               
    with open(zip_path, 'wb') as f:
        f.write(response.content)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:                                            # The data come in a zipfile so must unzip it
        zip_ref.extractall(savefolder)
    print(f'...... {timenow()} Download Complete')



def download_processed_data(url: str, filename: str, dest_dir: Path) -> bool:
    try:
        response = requests.get(url)
        response.raise_for_status()
        (dest_dir / filename).write_bytes(response.content)
        return True
    except requests.RequestException:
        return False


    
def fx_process_canfire_data():
    
    gdf = gpd.read_file(CAN_RAW_DATA_PATH)

    gdf = gdf[['YEAR', 'SIZE_HA', 'SRC_AGENCY', 'MAP_SOURCE', 'geometry']]
    gdf = gdf.rename(columns={'YEAR': 'fire_year'})
    gdf = gdf.rename(columns={'SIZE_HA': 'fire_size'})
    gdf = gdf.rename(columns={'SRC_AGENCY': 'province'}) 
    gdf["data_source"] = "CWFIS" 
    gdf = gdf.rename(columns={'MAP_SOURCE': 'data_aquisition'}) 

    gdf = gdf[gdf['province'] != 'QC']              # gets ride of all QC fires, but not the ones that are in natinal parks as these ones have province = the national park they are in

        

    gdf = repojectdata(gdf, 4326) 
   

    gdf.to_parquet(CAN_PROCESSED_DATA_PATH)
    shutil.rmtree(CAN_RAW_DATA_FOLDER_PATH)   

    return gdf









def fx_process_qcfire_data():   
    #################### ######################################## ######################################## ######################################## ####################
    # Merges the two datasets, reprojects it, then saves it as a parquet so we only have to do this once 
    #################### ######################################## ######################################## ######################################## ####################
    
    
    before_data = gpd.read_file(QC_BEFORE_RAW_DATA_PATH, layer= 'feux_anciens_prov')
    after_data = gpd.read_file(QC_AFTER_RAW_DATA_PATH, layer= 'feux_prov')

    after_data = after_data.drop(columns=['geoc_fmj','exercice', 'origine', 'met_at_str', 'shape_length', 'shape_area'])       
    before_data = before_data.drop(columns=['geoc_fan','exercice', 'origine', 'met_at_str', 'shape_length', 'shape_area'])       

    after_data = after_data.drop(columns=['perturb', 'an_perturb', 'part_str'])
    merged_data = gpd.GeoDataFrame(pd.concat([before_data, after_data], ignore_index=True),geometry='geometry')
    merged_data['an_origine'] = pd.to_numeric(merged_data['an_origine'], errors='coerce')
    merged_data['superficie'] = pd.to_numeric(merged_data['superficie'], errors='coerce')
    merged_data = merged_data.rename(columns={'an_origine': 'fire_year'})
    merged_data = merged_data.rename(columns={'superficie': 'fire_size'})
    merged_data["province"] = "QC"
    merged_data["data_source"] = "DQ"
    merged_data["data_aquisition"] = pd.NA

    merged_data = repojectdata(merged_data, 4326)

    
    merged_data.to_parquet(QC_PROCESSED_DATA_PATH)
    shutil.rmtree(QC_BEFORE_RAW_DATA_FOLDER_PATH) 
    shutil.rmtree(QC_AFTER_RAW_DATA_FOLDER_PATH) 

    return merged_data






def fx_process_watershed_data(gdf):
    gdf = gdf[["WSCSDA_EN", "geometry"]].rename(columns={"WSCSDA_EN": "watershed_name"})

    gdf = repojectdata(gdf, 4326)
    
    gdf.to_parquet(WATERSHED_PROCESSED_DATA_PATH)
    gdftogeojson=gdf
    gdftogeojson["geometry"] = gdftogeojson["geometry"].simplify(tolerance=0.01)            # Simplyfying the tolerance for the geojson watershed polygons to reduce server load 
    gdftogeojson.to_file(WATERSHED_PROCESSED_DATA_JSON_PATH, driver="GeoJSON") 
    
    
    
    






def fx_merge_provincial_fires(data1, data2):
    #################### ######################################## ######################################## ######################################## ####################
    # Merges two datasets
    #################### ######################################## ######################################## ######################################## ####################
    combined_gdf = pd.concat([data1, data2], ignore_index=True)

    combined_gdf = gpd.GeoDataFrame(combined_gdf, geometry='geometry', crs=data1.crs)
    
    combined_gdf.to_parquet(TOTALFIRE_DATA_PATH)  
    CAN_PROCESSED_DATA_PATH.unlink(missing_ok=True)
    QC_PROCESSED_DATA_PATH.unlink(missing_ok=True)
    return combined_gdf





POLYGON_MAX_BYTES = 10 * 1024 * 1024


def parse_polygon_geojson(document):
    """Validate a WGS84 polygon upload and combine its features into one area."""
    try:
        encoded = json.dumps(document, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
        size = len(encoded.encode("utf-8"))
        document = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("Boundary must contain valid JSON and finite coordinates.") from exc
    if size > POLYGON_MAX_BYTES:
        raise ValueError("Boundary must be 10 MB or smaller.")

    geometries = []

    def read_polygon(item):
        if not isinstance(item, dict):
            raise ValueError("Boundary must be a GeoJSON polygon, feature, or feature collection.")
        crs = item.get("crs")
        if crs is not None:
            if not isinstance(crs, dict) or not isinstance(crs.get("properties"), dict):
                raise ValueError("Boundary coordinates must use EPSG:4326 longitude/latitude.")
            if crs["properties"].get("name") not in {
                "EPSG:4326", "urn:ogc:def:crs:EPSG::4326",
                "urn:ogc:def:crs:OGC:1.3:CRS84", "OGC:CRS84",
            }:
                raise ValueError("Boundary coordinates must use EPSG:4326 longitude/latitude.")
        kind = item.get("type")
        if kind == "FeatureCollection":
            features = item.get("features")
            if not isinstance(features, list) or not features:
                raise ValueError("Boundary feature collection must not be empty.")
            for feature in features:
                if not isinstance(feature, dict) or feature.get("type") != "Feature":
                    raise ValueError("Feature collections must contain polygon features.")
                read_polygon(feature)
            return
        if kind == "Feature":
            read_polygon(item.get("geometry"))
            return
        if kind not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Boundary must contain only Polygon or MultiPolygon geometries.")
        coordinates = item.get("coordinates")
        polygons = [coordinates] if kind == "Polygon" else coordinates
        if not isinstance(polygons, list) or not polygons:
            raise ValueError("Boundary geometry must not be empty.")
        for rings in polygons:
            if not isinstance(rings, list) or not rings:
                raise ValueError("Each polygon must contain an outer ring.")
            for ring in rings:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("Polygon rings must be closed and contain at least four positions.")
                for position in ring:
                    if not isinstance(position, list) or len(position) not in (2, 3):
                        raise ValueError("Use longitude/latitude positions in the boundary.")
                    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in position):
                        raise ValueError("Boundary coordinates must be finite numbers.")
                    if not (-180 <= position[0] <= 180 and -90 <= position[1] <= 90):
                        raise ValueError("Boundary coordinates must use EPSG:4326 longitude/latitude.")
        try:
            geometry = shape(item)
        except (TypeError, ValueError) as exc:
            raise ValueError("Could not read the polygon geometry.") from exc
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("Boundary polygon is empty or invalid; check for crossing edges.")
        geometries.append(geometry)

    read_polygon(document)
    return unary_union(geometries)


def filter_number(value, label, *, integer=False, minimum=0):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
        if not math.isfinite(number) or number < minimum or (integer and not number.is_integer()):
            raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite {'whole ' if integer else ''}number of at least {minimum}.") from exc
    return int(number) if integer else number


def fx_filter_fires_data(
    fire_gdf, watershed_data, provincelist,
    min_year=None, max_year=None, min_size=None, max_size=None,
    distance_coords=None, distance_radius=None, watershed_name=None,
    polygon_geojson=None,
):
    """Apply all active filters to original fire geometries without modifying them."""
    if not isinstance(provincelist, list) or any(not isinstance(p, str) for p in provincelist):
        raise ValueError("Provinces must be a list of province codes.")
    filtered_gdf = fire_gdf if "ALL" in provincelist else fire_gdf[fire_gdf["province"].isin(provincelist)]
    min_year = filter_number(min_year, "Minimum year", integer=True)
    max_year = filter_number(max_year, "Maximum year", integer=True)
    min_size = filter_number(min_size, "Minimum size")
    max_size = filter_number(max_size, "Maximum size")
    for lower, upper, label in ((min_year, max_year, "year"), (min_size, max_size, "size")):
        if lower is not None and upper is not None and lower > upper:
            raise ValueError(f"Minimum {label} must not exceed maximum {label}.")
    for column, lower, upper in (("fire_year", min_year, max_year), ("fire_size", min_size, max_size)):
        if lower is not None:
            filtered_gdf = filtered_gdf[filtered_gdf[column] >= lower]
        if upper is not None:
            filtered_gdf = filtered_gdf[filtered_gdf[column] <= upper]

    user_point = buffer_deg = watershed_polygon = None
    coords = "" if distance_coords is None else distance_coords
    radius = filter_number(distance_radius, "Radius")
    if not isinstance(coords, str):
        raise ValueError("Coordinates must use latitude, longitude.")
    coords = coords.strip()
    if bool(coords) != (radius is not None):
        raise ValueError("Enter both coordinates and a radius, or leave both empty.")
    if coords:
        try:
            lat, lon = map(float, coords.split(","))
            if not (math.isfinite(lat) and math.isfinite(lon) and -80 <= lat <= 84 and -180 <= lon <= 180):
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("Coordinates must use latitude, longitude within the supported UTM area (-80 to 84 latitude).") from exc
        if radius <= 0:
            raise ValueError("Radius must be greater than zero.")
        user_point = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
        buffer_deg = user_point.to_crs(user_point.estimate_utm_crs()).buffer(radius * 1000).to_crs("EPSG:4326")
        buffer_filter = buffer_deg.to_crs(fire_gdf.crs).iloc[0]
        filtered_gdf = filtered_gdf[filtered_gdf.geometry.intersects(buffer_filter)]

    if watershed_name:
        if not isinstance(watershed_name, str):
            raise ValueError("Watershed name must be text.")
        selected_ws = watershed_data[watershed_data["watershed_name"] == watershed_name.strip()]
        if selected_ws.empty:
            raise ValueError(f'No watershed found with name "{watershed_name}".')
        watershed_polygon = selected_ws.geometry.union_all()
        watershed_filter = gpd.GeoSeries([watershed_polygon], crs=watershed_data.crs).to_crs(fire_gdf.crs).iloc[0]
        filtered_gdf = filtered_gdf[filtered_gdf.geometry.within(watershed_filter)]

    if polygon_geojson is not None:
        boundary = parse_polygon_geojson(polygon_geojson)
        boundary = gpd.GeoSeries([boundary], crs="EPSG:4326").to_crs(fire_gdf.crs).iloc[0]
        # Query the spatial index to avoid comparing every fire to a complex boundary.
        indices = filtered_gdf.sindex.query(boundary, predicate="intersects")
        filtered_gdf = filtered_gdf.iloc[sorted(indices)]

    return {
        "filtered_gdf": filtered_gdf.copy(),
        "user_point": user_point,
        "buffer_geom": buffer_deg,
        "watershed_polygon": watershed_polygon,
    }


def fx_download_json(filtered_data, MAX_SIZE_MB):    
    #################### ######################################## ######################################## ######################################## ####################
    # This function is to dowload the filtered data as a geojson 
    #################### ######################################## ######################################## ######################################## #################### 
                              
    geojson_data = json.loads(filtered_data.to_json())     
    

    MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
    geojson_bytes = len(json.dumps(geojson_data).encode('utf-8'))
    print(f'File size:{geojson_bytes/1000000}')
    if geojson_bytes > MAX_SIZE_BYTES:
        print(f'{geojson_bytes} is too big')
        return {"error": f"Data too large to load ({geojson_bytes / 1024 / 1024:.2f} MB). Please re-fresh and narrow your filter."}, 413


    geojson_string = json.dumps(geojson_data) 
    geojson_buffer = io.BytesIO(geojson_string.encode('utf-8'))   
    geojson_buffer.seek(0)

    return send_file(                                                                                       # Send the file back to the browser as an attachment

        geojson_buffer,
        
        mimetype='application/json',                   
        as_attachment=True,
        download_name='firecan_filtered_data.geojson'                   

    )





def fx_download_csv(filtered_data):             
    #################### ######################################## ######################################## ######################################## #################### #################### ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## #################### #################### ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## #################### #################### ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## #################### #################### ######################################## ######################################## ######################################## ####################
    # Exact same thing as the last function but downloads as csv
    #################### ######################################## ######################################## ######################################## #################### #################### ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## #################### #################### ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## #################### #################### ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## ######################################## #################### #################### ######################################## ######################################## ######################################## ####################
    csv_buffer = io.BytesIO()
    filtered_data.drop(columns=['geometry'], errors='ignore').to_csv(csv_buffer, index=False, encoding='utf-8')         # Drops geom column here too 
    csv_buffer.seek(0)
    
    return send_file(                                                   
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name='firecan_filtered_data.csv'
    ) 





def fx_download_gpkg(filtered_data, MAX_SIZE_MB):
    #################### ######################################## ######################################## ######################################## ####################
    # gpkg download
    #################### ######################################## ######################################## ######################################## #################### 
     
    
    gpkg_buffer = io.BytesIO()  

    filtered_data.to_file(gpkg_buffer, driver="GPKG")

    gpkg_buffer.seek(0) 



    MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
    gpkg_size = gpkg_buffer.getbuffer().nbytes
    print(f"GPKG size: {gpkg_size / 1024 / 1024:.2f} MB")

    if gpkg_size > MAX_SIZE_BYTES:
        print(f"{gpkg_size} bytes is too big")
        return {
            "error": f"Data too large to load ({gpkg_size / 1024 / 1024:.2f} MB). Please re-fresh and narrow your filter."
        }, 413
    

    return send_file(
        gpkg_buffer,
        mimetype='application/geopackage+sqlite3',
        as_attachment=True,
        download_name='firecan_filtered_data.gpkg'
    )



















































































































































#################### ######################################## ######################################## ######################################## ####################
# Function Graveyard
#################### ######################################## ######################################## ######################################## ####################

#CANFIRE WITH PARKS CANADA IMBEDED INTO THE DATASET
# def fx_process_canfire_data():
    
#     gdf = gpd.read_file(CAN_RAW_DATA_PATH)

#     gdf = gdf[['YEAR', 'SIZE_HA', 'SRC_AGENCY', 'MAP_SOURCE', 'geometry']]
#     gdf = gdf.rename(columns={'YEAR': 'fire_year'})
#     gdf = gdf.rename(columns={'SIZE_HA': 'fire_size'})
#     gdf = gdf.rename(columns={'SRC_AGENCY': 'province'}) 
#     gdf["data_source"] = "CWFIS" 
#     gdf = gdf.rename(columns={'MAP_SOURCE': 'data_aquisition'}) 

#     pc_codes = ['PC-PA','PC-WB','PC-JA','PC-NA','PC-RM','PC-EI','PC-BA','PC-KO','PC-LM','PC-GL','PC-PU','PC-VU','PC-YO','PC-SY','PC-GR','PC-WP','PC-RE','PC-TN','PC-WL','PC-NI']
#     pc_to_province = {'PC-PA':'SK', 'PC-WB':'AB', 'PC-JA':'AB', 'PC-NA':'NT', 'PC-RM':'MB','PC-EI':'AB', 'PC-BA':'AB', 'PC-KO':'QC', 'PC-LM':'QC', 'PC-GL':'QC','PC-PU':'QC', 'PC-VU':'QC', 'PC-YO':'YT', 'PC-SY':'NT', 'PC-GR':'AB','PC-WP':'MB', 'PC-RE':'QC', 'PC-TN':'QC', 'PC-WL':'ON', 'PC-NI':'ON'}
#     parks_decoded = {'PC-PA': 'Prince Albert National Park','PC-WB': 'Wood Buffalo National Park','PC-JA': 'Jasper National Park','PC-NA': 'Nahanni National Park','PC-RM': 'Riding Mountain National Park','PC-EI': 'Elk Island National Park','PC-BA': 'Banff National Park','PC-KO': 'Kootenay National Park','PC-LM': 'La Mauricie National Park','PC-GL': 'Glacier National Park', 'PC-PU': 'Pukaskwa National Park','PC-VU': 'Vuntut National Park','PC-YO': 'Yoho National Park','PC-SY': 'Saoyú-ehdacho National Historic Site','PC-GR': 'Grasslands National Park','PC-WP': 'Wapusk National Park','PC-RE': 'Mount Revelstoke National Park','PC-TN': 'Terra Nova National Park','PC-WL': 'Waterton Lakes National Park','PC-NI': 'PC-NI'}

#     gdf = gdf[gdf['province'] != 'QC']              # gets ride of all QC fires, but not the ones that are in natinal parks as these ones have province = the national park they are in
#     gdf['pc'] = gdf['province'].where(gdf['province'].isin(pc_codes), '')     # creating parks column that contains only the provinces that had a parks code as the province   
#     gdf['pc'] = gdf['pc'].replace(parks_decoded)                            # in the parks column we change their parks code to an easier parks code 
#     gdf['province'] = gdf['province'].replace(pc_to_province)    # Now we change all the province park codes to province codes in the province column
        

#     gdf = repojectdata(gdf, 4326) 
   

#     gdf.to_parquet(CAN_PROCESSED_DATA_PATH)
#     shutil.rmtree(CAN_RAW_DATA_FOLDER_PATH)   

#     return gdf



# def fx_process_watershed_data():
#     #################### ######################################## ######################################## ######################################## ####################
#     # This function gets the watershed data, it then reads it in, drops some columns, and reprojects it, it also gives each watershed a unique name
#     #################### ######################################## ######################################## ######################################## ####################       
                                                                
#     watershed_data = gpd.read_file(WATERSHED_RAW_DATA_PATH, layer=1)

#     watershed_data = watershed_data[watershed_data['NIVEAU_BASSIN'] == 1]
#     watershed_data = watershed_data.drop(columns=['NO_COURS_DEAU','NO_SEQ_COURS_DEAU','IDENTIFICATION_COMPLETE', 'NOM_COURS_DEAU_MINUSCULE', 'NIVEAU_BASSIN', 'ECHELLE', 'SUPERF_KM2', 'NO_SEQ_BV_PRIMAIRE', 'NOM_BV_PRIMAIRE', 'NO_REG_HYDRO', 'NOM_REG_HYDRO_ABREGE', 'Shape_Length', 'Shape_Area']) # might want shape length and share area later
    
    
#     watershed_data = watershed_data.copy()
#     mask = watershed_data['NOM_COURS_DEAU'].isna() | (watershed_data['NOM_COURS_DEAU'].str.strip() == "")
#     watershed_data.loc[mask, 'NOM_COURS_DEAU'] = [
#         f"unnamed_{i+1}" for i in range(mask.sum())
#     ]   # making it so each watershed has a unique name (there are multiple watersheds with same name)
#     watershed_data['NOM_COURS_DEAU'] = watershed_data.groupby('NOM_COURS_DEAU').cumcount().add(1).astype(str).radd(watershed_data['NOM_COURS_DEAU'] + "-")


    
#     watershed_data = repojectdata(watershed_data, 4326)

    
#     watershed_data.to_parquet(WATERSHED_PROCESSED_DATA_PATH)  
#     watershed_data_togeojson=watershed_data
#     watershed_data_togeojson["geometry"] = watershed_data_togeojson["geometry"].simplify(tolerance=0.01)            # Simplyfying the tolerance for the geojson watershed polygons to reduce server load 
#     watershed_data_togeojson.to_file(WATERSHED_PROCESSED_DATA_JSON_PATH, driver="GeoJSON")                                 # saving as static geojson to be sent for watershed explorer
#     shutil.rmtree(WATERSHED_RAW_DATA_FOLDER_PATH) 

#     return watershed_data










# def fx_get_can_fire_data():
#     #################### ######################################## ######################################## ######################################## ####################
#     # Loads in QC fire data (beofre and after), merges the two datasets, reprojects it, then saves it as a parquet so we only have to do this once 
#     #################### ######################################## ######################################## ######################################## ####################
#     print('Getting Can Fire Data')                                             

#     canfire_unzipped_file_path = fx_get_url_request(
#     'canfire',
#     'https://cwfis.cfs.nrcan.gc.ca/downloads/nfdb/fire_poly/current_version/NFDB_poly.zip',
#     'NFDB_poly.zip',
#     "NFDB_poly_1972to2020_20250630.shp"
#     )          # Downloading data
   
#     can_processed_data_folder_path = work_dir / "data" / 'processed_data'                                                   
#     can_processed_data_path = can_processed_data_folder_path / 'can_processed_fire_data.parquet'                # creating path for processed daata

#     if not can_processed_data_path.exists():# Check if data exists
#         print(f'........ {timenow()} Pre-Processing data now')
#         if not can_processed_data_folder_path.exists():
#             can_processed_data_folder_path.mkdir(parents=True, exist_ok=True) # makes file for processed data
#         print(f'.......... {timenow()} Loading in Canada Data')

        
#         gdf = gpd.read_file(canfire_unzipped_file_path)

#         gdf = gdf[['YEAR', 'SIZE_HA', 'SRC_AGENCY', 'geometry']]
#         gdf = gdf.rename(columns={'YEAR': 'fire_year'})
#         gdf = gdf.rename(columns={'SIZE_HA': 'fire_size'})
#         gdf = gdf.rename(columns={'SRC_AGENCY': 'province'})  

#         pc_codes = ['PC-PA','PC-WB','PC-JA','PC-NA','PC-RM','PC-EI','PC-BA','PC-KO','PC-LM','PC-GL','PC-PU','PC-VU','PC-YO','PC-SY','PC-GR','PC-WP','PC-RE','PC-TN','PC-WL','PC-NI']
#         pc_to_province = {'PC-PA':'SK', 'PC-WB':'AB', 'PC-JA':'AB', 'PC-NA':'NT', 'PC-RM':'MB','PC-EI':'AB', 'PC-BA':'AB', 'PC-KO':'QC', 'PC-LM':'QC', 'PC-GL':'QC','PC-PU':'QC', 'PC-VU':'QC', 'PC-YO':'YT', 'PC-SY':'NT', 'PC-GR':'AB','PC-WP':'MB', 'PC-RE':'QC', 'PC-TN':'QC', 'PC-WL':'ON', 'PC-NI':'ON'}
#         parks_decoded = {'PC-PA': 'Prince Albert National Park','PC-WB': 'Wood Buffalo National Park','PC-JA': 'Jasper National Park','PC-NA': 'Nahanni National Park','PC-RM': 'Riding Mountain National Park','PC-EI': 'Elk Island National Park','PC-BA': 'Banff National Park','PC-KO': 'Kootenay National Park','PC-LM': 'La Mauricie National Park','PC-GL': 'Glacier National Park', 'PC-PU': 'Pukaskwa National Park','PC-VU': 'Vuntut National Park','PC-YO': 'Yoho National Park','PC-SY': 'Saoyú-ehdacho National Historic Site','PC-GR': 'Grasslands National Park','PC-WP': 'Wapusk National Park','PC-RE': 'Mount Revelstoke National Park','PC-TN': 'Terra Nova National Park','PC-WL': 'Waterton Lakes National Park','PC-NI': 'PC-NI'}

#         gdf = gdf[gdf['province'] != 'QC']              # gets ride of all QC fires, but not the ones that are in natinal parks as these ones have province = the national park they are in
#         gdf['pc'] = gdf['province'].where(gdf['province'].isin(pc_codes), '')     # creating parks column that contains only the provinces that had a parks code as the province   
#         gdf['pc'] = gdf['pc'].replace(parks_decoded)                            # in the parks column we change their parks code to an easier parks code 
#         gdf['province'] = gdf['province'].replace(pc_to_province)    # Now we change all the province park codes to province codes in the province column
         

#         print(f'............ {timenow()} Re-Projecting Data')
#         gdf = repojectdata(gdf, 4326) 

#         print(f'............ {timenow()} Done Pre-Processing saving for later use')     

#         gdf.to_parquet(can_processed_data_path)
#     else:               
#         print(f'........ {timenow()} The CAN data is already processed loading in now')                                                                                                # If there fire data is already processed we just load it in here
#         gdf = gpd.read_parquet(can_processed_data_path)

#     return gdf










# def fx_get_qc_fire_data():   
#     #################### ######################################## ######################################## ######################################## ####################
#     # Loads in QC fire data (beofre and after), merges the two datasets, reprojects it, then saves it as a parquet so we only have to do this once 
#     #################### ######################################## ######################################## ######################################## ####################

#     print('Getting QC Fire Data')                                               
#     url_qcfires_after76 = 'https://diffusion.mffp.gouv.qc.ca/Diffusion/DonneeGratuite/Foret/PERTURBATIONS_NATURELLES/Feux_foret/02-Donnees/PROV/FEUX_PROV_GPKG.zip'
#     qcfires_after76_zipname = 'FEUX_PROV_GPKG.zip'                                                         
#     qcfires_after76_gpkgname = 'FEUX_PROV.gpkg'


#     url_qcfires_before76 = 'https://diffusion.mffp.gouv.qc.ca/Diffusion/DonneeGratuite/Foret/PERTURBATIONS_NATURELLES/Feux_foret/02-Donnees/PROV/FEUX_ANCIENS_PROV_GPKG.zip'
#     qcfires_before76_zipname = 'FEUX_PROV_GPKG.zip'
#     qcfires_before76_gpkgname = 'FEUX_ANCIENS_PROV.gpkg'


#     qcfires_before76_unzipped_file_path = fx_get_url_request('qcfires_before76', url_qcfires_before76, qcfires_before76_zipname, qcfires_before76_gpkgname)
#     qcfires_after76_unzipped_file_path = fx_get_url_request('qcfires_after76', url_qcfires_after76, qcfires_after76_zipname, qcfires_after76_gpkgname)          # DOwnloading data

#     qc_processed_data_folder_path = work_dir / "data" / 'processed_data'
#     qc_processed_data_path = qc_processed_data_folder_path / 'qc_processed_fire_data.parquet'

#     if not qc_processed_data_path.exists():
#         print(f'........ {timenow()} Pre-Processing data now')
#         qc_processed_data_folder_path.mkdir(parents=True, exist_ok=True)
#         print(f'.......... {timenow()} Loading and Merging QC data')
#         before_data = gpd.read_file(qcfires_before76_unzipped_file_path, layer= 'feux_anciens_prov')
#         after_data = gpd.read_file(qcfires_after76_unzipped_file_path, layer= 'feux_prov')

#         after_data = after_data.drop(columns=['geoc_fmj','exercice', 'origine', 'met_at_str', 'shape_length', 'shape_area'])       
#         before_data = before_data.drop(columns=['geoc_fan','exercice', 'origine', 'met_at_str', 'shape_length', 'shape_area'])       

#         after_data = after_data.drop(columns=['perturb', 'an_perturb', 'part_str'])
#         merged_data = gpd.GeoDataFrame(pd.concat([before_data, after_data], ignore_index=True),geometry='geometry')
#         merged_data['an_origine'] = pd.to_numeric(merged_data['an_origine'], errors='coerce')
#         merged_data['superficie'] = pd.to_numeric(merged_data['superficie'], errors='coerce')
#         merged_data = merged_data.rename(columns={'an_origine': 'fire_year'})
#         merged_data = merged_data.rename(columns={'superficie': 'fire_size'})
#         merged_data["province"] = "QC"
        
#         print(f'.......... {timenow()} Re-Projecting Data')
#         merged_data = repojectdata(merged_data, 4326)

#         print(f'............ {timenow()} Done Pre-Processing saving for later use')
#         merged_data.to_parquet(qc_processed_data_path)

#     else:               
#         print(f'........ {timenow()} The QC data is already processed Loading in now')                           # If there fire data is already processed we just load it in here
#         merged_data = gpd.read_parquet(qc_processed_data_path)

#     return merged_data













# def fx_scrape_ontariogeohub(url, dataname):
#     print(f'.. {timenow()} Scrapping Ontario Geohub')
#     savefolder = work_dir / "data" / dataname
#     data_path = savefolder / f"unprocessed_{dataname}.parquet"

#     if not data_path.exists(): 
#         print(f'.... {timenow()} The data does not exist, trying to download now')
#         try:
#             ids_response = requests.get(
#                 url,
#                 params={
#                     "where": "1=1",
#                     "returnIdsOnly": "true",
#                     "f": "json"
#                 }
#             )
#             ids = ids_response.json()["objectIds"]
#         except:
#             print("Could Not acces Ontario Geohub, their API sucks :(, Unprocessed Ontario Fire Data is available on the git hub, put the .parquet file in the data/ontario_fires folder and run again))")
#             sys.exit()

        
#         all_feats = []
#         chunk_size = 500

#         for i in range(0, len(ids), chunk_size):
#             batch = ids[i:i + chunk_size]
#             res = requests.post(
#                 url,
#                 data={
#                     "objectIds": ",".join(map(str, batch)),
#                     "outFields": "*",
#                     "outSR": 4326,
#                     "returnGeometry": "true",
#                     "f": "json"
#                 }
#             ).json()



#             features = res.get("features", [])
#             for feat in features:
#                 geom_data = feat.get("geometry")
#                 props = feat.get("attributes", {})

                
#                 geom = None
#                 if geom_data:
#                     try:
#                         if "rings" in geom_data:   
#                             geom = Polygon(geom_data["rings"][0])
#                         elif "paths" in geom_data:  
#                             geom = shape({"type": "LineString", "coordinates": geom_data["paths"][0]})
#                         elif "x" in geom_data and "y" in geom_data:  
#                             geom = shape({"type": "Point", "coordinates": [geom_data["x"], geom_data["y"]]})
#                     except Exception as e:
#                         print("⚠️ Geometry conversion failed for one feature:", e)
#                         continue

#                 if geom:
#                     props["geometry"] = geom
#                     all_feats.append(props)
#         print(f'...... {timenow()} The Data is downloaded saving now for later use')

#         savefolder.mkdir(parents=True, exist_ok=True)

#         gdf = gpd.GeoDataFrame(all_feats, geometry="geometry", crs="EPSG:4326")

#         gdf.to_parquet(data_path) 
#     else:
#         print(f'.... {timenow()} The Data is already downlaoded ')

#     return data_path


# def fx_get_on_fire_data():
#     print('Getting ON Fire Data')                                               # Loads in QC fire data (beofre and after), merges the two datasets, reprojects it, then saves it as a parquet so we only have to do this once 

#     ontario_fires_URL = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open09/MapServer/28/query"
#     data_path = fx_scrape_ontariogeohub(ontario_fires_URL, 'ontario_fires')

#     on_processed_data_folder_path = work_dir / "data" / 'on_processed_data'
#     on_processed_data_path = on_processed_data_folder_path / 'on_processed_fire_data.parquet'

#     if not on_processed_data_path.exists():
#         print(f'...... {timenow()} Pre-Processing the Data')

#         on_processed_data_folder_path.mkdir(parents=True, exist_ok=True)
#         data = gpd.read_parquet(data_path)
#         data = data[["FIRE_YEAR", "FIRE_FINAL_SIZE", "geometry"]]
#         data = data.rename(columns={"FIRE_YEAR": "fire_year"})
#         data = data.rename(columns={"FIRE_FINAL_SIZE": "fire_size"})
#         data["province"] = "on"
#         data = repojectdata(data, 4326)
#         print(f'........ {timenow()} Done Pre-Processing Saving For Later')

#         data.to_parquet(on_processed_data_path) 
#     else:
#         print(f'...... {timenow()} The Data Is Already Pre-Processed Loading In Now')
#         data = gpd.read_parquet(on_processed_data_path)
#     return data



# def fx_createexploremap(data, map_name):
#     m = data.explore()
#     m.save(f'static/{map_name}.html')
#     print("saved")