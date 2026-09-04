


import zipfile
import json
import requests
import geopandas as gpd
from datetime import datetime
from flask import send_file   # type: ignore
import io
from pathlib import Path
import pandas as pd
from shapely.geometry import Point
import numpy as np
import requests
import json
import geopandas as gpd
from shapely.geometry import shape, Polygon, MultiPolygon, mapping
from pathlib import Path
from datetime import datetime
import sys
import math
import shutil


work_dir  = Path.cwd()
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


    
def fx_process_canfire_data():
    
    gdf = gpd.read_file(CAN_RAW_DATA_PATH)

    gdf = gdf[['YEAR', 'SIZE_HA', 'SRC_AGENCY', 'geometry']]
    gdf = gdf.rename(columns={'YEAR': 'fire_year'})
    gdf = gdf.rename(columns={'SIZE_HA': 'fire_size'})
    gdf = gdf.rename(columns={'SRC_AGENCY': 'province'})  

    pc_codes = ['PC-PA','PC-WB','PC-JA','PC-NA','PC-RM','PC-EI','PC-BA','PC-KO','PC-LM','PC-GL','PC-PU','PC-VU','PC-YO','PC-SY','PC-GR','PC-WP','PC-RE','PC-TN','PC-WL','PC-NI']
    pc_to_province = {'PC-PA':'SK', 'PC-WB':'AB', 'PC-JA':'AB', 'PC-NA':'NT', 'PC-RM':'MB','PC-EI':'AB', 'PC-BA':'AB', 'PC-KO':'QC', 'PC-LM':'QC', 'PC-GL':'QC','PC-PU':'QC', 'PC-VU':'QC', 'PC-YO':'YT', 'PC-SY':'NT', 'PC-GR':'AB','PC-WP':'MB', 'PC-RE':'QC', 'PC-TN':'QC', 'PC-WL':'ON', 'PC-NI':'ON'}
    parks_decoded = {'PC-PA': 'Prince Albert National Park','PC-WB': 'Wood Buffalo National Park','PC-JA': 'Jasper National Park','PC-NA': 'Nahanni National Park','PC-RM': 'Riding Mountain National Park','PC-EI': 'Elk Island National Park','PC-BA': 'Banff National Park','PC-KO': 'Kootenay National Park','PC-LM': 'La Mauricie National Park','PC-GL': 'Glacier National Park', 'PC-PU': 'Pukaskwa National Park','PC-VU': 'Vuntut National Park','PC-YO': 'Yoho National Park','PC-SY': 'Saoyú-ehdacho National Historic Site','PC-GR': 'Grasslands National Park','PC-WP': 'Wapusk National Park','PC-RE': 'Mount Revelstoke National Park','PC-TN': 'Terra Nova National Park','PC-WL': 'Waterton Lakes National Park','PC-NI': 'PC-NI'}

    gdf = gdf[gdf['province'] != 'QC']              # gets ride of all QC fires, but not the ones that are in natinal parks as these ones have province = the national park they are in
    gdf['pc'] = gdf['province'].where(gdf['province'].isin(pc_codes), '')     # creating parks column that contains only the provinces that had a parks code as the province   
    gdf['pc'] = gdf['pc'].replace(parks_decoded)                            # in the parks column we change their parks code to an easier parks code 
    gdf['province'] = gdf['province'].replace(pc_to_province)    # Now we change all the province park codes to province codes in the province column
        

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
    

    merged_data = repojectdata(merged_data, 4326)

    
    merged_data.to_parquet(QC_PROCESSED_DATA_PATH)
    shutil.rmtree(QC_BEFORE_RAW_DATA_FOLDER_PATH) 
    shutil.rmtree(QC_AFTER_RAW_DATA_FOLDER_PATH) 

    return merged_data
















def fx_process_watershed_data():
    #################### ######################################## ######################################## ######################################## ####################
    # This function gets the watershed data, it then reads it in, drops some columns, and reprojects it, it also gives each watershed a unique name
    #################### ######################################## ######################################## ######################################## ####################       
                                                                
    watershed_data = gpd.read_file(WATERSHED_RAW_DATA_PATH, layer=1)

    watershed_data = watershed_data[watershed_data['NIVEAU_BASSIN'] == 1]
    watershed_data = watershed_data.drop(columns=['NO_COURS_DEAU','NO_SEQ_COURS_DEAU','IDENTIFICATION_COMPLETE', 'NOM_COURS_DEAU_MINUSCULE', 'NIVEAU_BASSIN', 'ECHELLE', 'SUPERF_KM2', 'NO_SEQ_BV_PRIMAIRE', 'NOM_BV_PRIMAIRE', 'NO_REG_HYDRO', 'NOM_REG_HYDRO_ABREGE', 'Shape_Length', 'Shape_Area']) # might want shape length and share area later
    
    
    watershed_data = watershed_data.copy()
    mask = watershed_data['NOM_COURS_DEAU'].isna() | (watershed_data['NOM_COURS_DEAU'].str.strip() == "")
    watershed_data.loc[mask, 'NOM_COURS_DEAU'] = [
        f"unnamed_{i+1}" for i in range(mask.sum())
    ]   # making it so each watershed has a unique name (there are multiple watersheds with same name)
    watershed_data['NOM_COURS_DEAU'] = watershed_data.groupby('NOM_COURS_DEAU').cumcount().add(1).astype(str).radd(watershed_data['NOM_COURS_DEAU'] + "-")


    
    watershed_data = repojectdata(watershed_data, 4326)

    
    watershed_data.to_parquet(WATERSHED_PROCESSED_DATA_PATH)  
    watershed_data_togeojson=watershed_data
    watershed_data_togeojson["geometry"] = watershed_data_togeojson["geometry"].simplify(tolerance=0.01)            # Simplyfying the tolerance for the geojson watershed polygons to reduce server load 
    watershed_data_togeojson.to_file(WATERSHED_PROCESSED_DATA_JSON_PATH, driver="GeoJSON")                                 # saving as static geojson to be sent for watershed explorer
    shutil.rmtree(WATERSHED_RAW_DATA_FOLDER_PATH) 

    return watershed_data





def fx_merge_provincial_fires(data1, data2):
    #################### ######################################## ######################################## ######################################## ####################
    # Merges two datasets
    #################### ######################################## ######################################## ######################################## ####################
    combined_gdf = pd.concat([data1, data2], ignore_index=True)

    combined_gdf = gpd.GeoDataFrame(combined_gdf, geometry='geometry', crs=data1.crs)
    unique_provinces = combined_gdf['province'].unique()
    
    combined_gdf.to_parquet(TOTALFIRE_DATA_PATH)  
    CAN_PROCESSED_DATA_PATH.unlink(missing_ok=True)
    QC_PROCESSED_DATA_PATH.unlink(missing_ok=True)
    return combined_gdf





def fx_filter_fires_data(                                                                             # This is the function that actually filters the data, it takes in fire data (and watershed but removed it cause brocken for now), as well as user inputs for filtering 
    fire_gdf,      
    watershed_data, 
    provincelist,                                                                                                                                                                   # Nore sure if i already mentioned this but i used AI to help apply all the filters at once / apply only the ones the user inputed
    min_year,
    max_year,
    min_size,
    max_size,
    distance_coords,
    distance_radius,
    watershed_name,
    pc_name
    ):
    #################### ######################################## ######################################## ######################################## ####################
    # Filters data set by storing conditions in list and then applyign them all at once, returning all the polygons necessary depending on the fitlers used
    #################### ######################################## ######################################## ######################################## ####################
    if "ALL" in provincelist:
        filtered_gdf = fire_gdf
    elif pc_name != '':                 # if provincial park filtering is selected just include all the provinces
        filtered_gdf = fire_gdf[fire_gdf['pc'] == pc_name]
    else:  
        filtered_gdf = fire_gdf[fire_gdf['province'].isin(provincelist)]
    
    conditions = []     # List of filtering conditions 
    
    if min_year  != '' or max_year  != '':                                                           # This IFs for all of these check if the filtering box on the site has a value inputed in it for this one and the next one we use OR becuase wse want the use to be able to input only a max or a min and not HAVE to input both 
        if min_year  != '':
            min_year = int(min_year)
        else:                                                                                               # If this field was empty (and the other was not as the IF is running) then we assing the min year to 0, if we dont do this it tryus to convert NULL to an int
            min_year = 0
        if max_year  != '':
            max_year= int(max_year)
        else:
            max_year = 100000
        conditions.append((filtered_gdf['fire_year'] >= min_year) & (filtered_gdf['fire_year'] <= max_year))      # This appends the condition to the filtering list to be applied later 

    if min_size  != '' or max_size  != '':
        if min_size  != '':
            min_size = float(min_size)
        else:
            min_size = 0.0
        if max_size  != '':
            max_size= float(max_size)
        else:
            max_size = 100000.0
        print('here')
        conditions.append((filtered_gdf['fire_size'] >= min_size) & (filtered_gdf['fire_size'] <= max_size))

    if distance_coords  != '' and distance_radius  != '':                                                     # The is the distance radius filtering that only selects fires within a radius of a point 
            lat, lon = map(float, distance_coords.split(','))       
            distance_radius = float(distance_radius)
            distance_radius = distance_radius*1000
            user_point = gpd.GeoSeries([Point(lon, lat)], crs='EPSG:4326')                                    # This creates the point based ont he user inputed coords 
            utm_crs = user_point.estimate_utm_crs()                             
            user_point_m = user_point.to_crs(utm_crs)                                                             # This chanes the point to a projection that makes sense for its locatoin, we cannot have it in EPSG: 4326 becuase this projection cant measure distances in metres only in degrees 
            buffer_m = user_point_m.buffer(distance_radius)                                                         # This creates a buffer around the point with a radius that the user inputed 
            buffer_deg = buffer_m.to_crs('EPSG:4326')                                                             # Here we reproject the buffer back to EPSG:4326 so leaflet can display it
            conditions.append(filtered_gdf.geometry.intersects(buffer_deg.iloc[0]))

    if watershed_name  != '':  
            selected_ws = watershed_data[watershed_data['NOM_COURS_DEAU'] == watershed_name]
            print(selected_ws)
            if not selected_ws.empty:
                print('Starting Watershed Filtering', timenow())
                watershed_polygon = selected_ws.geometry.unary_union  
                conditions.append(filtered_gdf.geometry.within(watershed_polygon))
                print('Done Watershed Filtering', timenow())
            else:
                print(f'No watershed found with name "{watershed_name}". Filter will be ignored.')




    if conditions:
        combined_mask = np.logical_and.reduce(conditions)                                                         # The combined filtered conditions
        filtered_gdf = filtered_gdf[combined_mask]                                                                # Filtering the dataset and returning with the right fitlers 

    results = {                                     # we have multiple things being returned depending on the filtering options used 
            "filtered_gdf": filtered_gdf,
            "user_point": None,
            "buffer_geom": None,
            "watershed_polygon": None
        }

    
    if distance_coords != '' and distance_radius != '':
        results["user_point"] = user_point
        results["buffer_geom"] = buffer_deg

    if watershed_name != '' and watershed_polygon is not None:
        results["watershed_polygon"] = watershed_polygon

    return results





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