import zipfile
import json
import requests
import geopandas as gpd
from datetime import datetime
from flask import send_file   # type: ignore
import io
from pathlib import Path
import pandas as pd
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union
import math
import shutil
import shapely
import numpy as np
import threading
import pyarrow as pa
import pyarrow.parquet as pq
try:
    import fcntl                                                                                # lets several Gunicorn workers share one download
except ImportError:                                                                             # Windows, which only runs the dev server
    fcntl = None



work_dir = Path(__file__).resolve().parent.parent
DATA_FOLDER_PATH = work_dir / 'data'
PROCESSED_DATA_FOLDER_PATH = DATA_FOLDER_PATH / "processed_data"
CAN_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / "can_processed_fire_data.parquet"  # processed data output
CAN_RAW_DATA_FOLDER_PATH = DATA_FOLDER_PATH / "canfire"
QC_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'qc_processed_fire_data.parquet'
QC_BEFORE_RAW_DATA_FOLDER_PATH = DATA_FOLDER_PATH / 'qcfires_before76' 
QC_AFTER_RAW_DATA_FOLDER_PATH = DATA_FOLDER_PATH / 'qcfires_after76' 
QC_BEFORE_RAW_DATA_PATH = QC_BEFORE_RAW_DATA_FOLDER_PATH / 'FEUX_ANCIENS_PROV.gpkg'
QC_AFTER_RAW_DATA_PATH = QC_AFTER_RAW_DATA_FOLDER_PATH / 'FEUX_PROV.gpkg'
WATERSHED_PROCESSED_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'watershed_data.parquet'
WATERSHED_PROCESSED_DATA_JSON_PATH = work_dir/ 'static' / 'watershed_data.geojson'
TOTALFIRE_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'TotalFire_data.parquet'
FIRE_DATA_GIT_URL = 'https://github.com/thomascheung05/FIRECAN/releases/download/DataV1/TotalFire_data.parquet'
FIRE_DISPLAY_GIT_URL = 'https://github.com/thomascheung05/FIRECAN/releases/download/DataV1/TotalFire_display50m.parquet'
FIRE_DISPLAY_DATA_PATH = PROCESSED_DATA_FOLDER_PATH / 'TotalFire_display50m.parquet'
FIRE_DISPLAY_TOLERANCE_M = 50                                                                  # the in memory copy is simplified to this, matches the map's default display tolerance
FIRE_ROW_GROUP_SIZE = 1000                                                                      # small row groups so reading a few fires' full geometry only reads a little of the file
BBOX_COLUMNS = ['bbox_minx', 'bbox_miny', 'bbox_maxx', 'bbox_maxy']                             # exact bounds of the full detail geometry, kept in the display copy
COORD_DECIMALS = 5                                                                              # 5 decimal places in EPSG:4326 is ~1 m, plenty for fire/watershed boundaries



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





def reduce_coord_precision(gdf, decimals=COORD_DECIMALS):
    #################### ######################################## ######################################## ######################################## ####################
    # Snaps polygon coordinates to a grid of 10^-decimals degrees (drops excess decimal places), keeps geometries valid, drops any that collapse to empty
    #################### ######################################## ######################################## ######################################## ####################
    print('............',timenow(), ' Simplifying data')
    gdf = gdf.copy()
    gdf["geometry"] = shapely.set_precision(gdf.geometry.values, grid_size=10 ** -decimals)
    empty = gdf.geometry.is_empty | gdf.geometry.isna()
    if empty.any():
        print(f'............ {empty.sum()} polygons collapsed after reducing precision, dropping them')
    return gdf[~empty]





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
    #################### ######################################## ######################################## ######################################## ####################
    # Download something using request.get() and unpack the zip 
    #################### ######################################## ######################################## ######################################## ####################    

    try:
        response = requests.get(url)
        response.raise_for_status()
        (dest_dir / filename).write_bytes(response.content)
        return True
    except requests.RequestException:
        return False


    
def fx_process_canfire_data():
    #################### ######################################## ######################################## ######################################## ####################
    # Read in, drop/rename columns, remove QC fires, reproject, save, delete raw data 
    #################### ######################################## ######################################## ######################################## ####################    
    
    shapefiles = sorted(CAN_RAW_DATA_FOLDER_PATH.glob('NFDB_poly_*.shp'))         # the NFDB zip is split by period (e.g. 1972to2020 and 2021to2024), read every part
    if not shapefiles:
        raise FileNotFoundError(f'No NFDB_poly_*.shp files found in {CAN_RAW_DATA_FOLDER_PATH}')
    parts = []
    for shp in shapefiles:
        print(f'............ {timenow()} Reading {shp.name}')
        part = gpd.read_file(shp)
        part = part[['YEAR', 'SIZE_HA', 'SRC_AGENCY', 'MAP_SOURCE', 'geometry']]
        parts.append(repojectdata(part, 4326))
    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry='geometry', crs=parts[0].crs)

    gdf = gdf.rename(columns={'YEAR': 'fire_year'})
    gdf = gdf.rename(columns={'SIZE_HA': 'fire_size'})
    gdf = gdf.rename(columns={'SRC_AGENCY': 'province'}) 
    gdf["data_source"] = "CWFIS" 
    gdf = gdf.rename(columns={'MAP_SOURCE': 'data_aquisition'}) 

    gdf = gdf[gdf['province'] != 'QC']              # gets ride of all QC fires, but not the ones that are in natinal parks as these ones have province = the national park they are in

        

    gdf = repojectdata(gdf, 4326) 
    gdf = reduce_coord_precision(gdf)
   

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
    merged_data = reduce_coord_precision(merged_data)

    
    merged_data.to_parquet(QC_PROCESSED_DATA_PATH)
    shutil.rmtree(QC_BEFORE_RAW_DATA_FOLDER_PATH) 
    shutil.rmtree(QC_AFTER_RAW_DATA_FOLDER_PATH) 

    return merged_data






def fx_process_watershed_data(gdf):
    #################### ######################################## ######################################## ######################################## ####################
    # raname, reproject, save as parquest AND geojson  
    #################### ######################################## ######################################## ######################################## ####################    

    gdf = gdf[["WSCSDA_EN", "geometry"]].rename(columns={"WSCSDA_EN": "watershed_name"})

    gdf = repojectdata(gdf, 4326)
    gdf = reduce_coord_precision(gdf)
    
    gdf.to_parquet(WATERSHED_PROCESSED_DATA_PATH)
    gdftogeojson=gdf.copy()
    gdftogeojson["geometry"] = gdftogeojson["geometry"].simplify(tolerance=0.01)            # Simplyfying the tolerance for the geojson watershed polygons to reduce server load 
    gdftogeojson.to_file(WATERSHED_PROCESSED_DATA_JSON_PATH, driver="GeoJSON") 

    return gdf
    
    
    
    






def fx_build_fire_files(gdf, full_path=TOTALFIRE_DATA_PATH, display_path=FIRE_DISPLAY_DATA_PATH):
    #################### ######################################## ######################################## ######################################## ####################
    # Saves the fire data as two files that line up row for row:
    #   full_path    - full detail geometry, sorted by location in small row groups so fx_read_fire_geometry only reads the groups holding the fires it needs
    #   display_path - attributes, each fire's exact bounds and geometry simplified to FIRE_DISPLAY_TOLERANCE_M, small enough to keep in memory for filtering and the map
    #################### ######################################## ######################################## ######################################## ####################
    gdf = gdf.iloc[gdf.geometry.hilbert_distance().argsort(kind='stable')].reset_index(drop=True)      # nearby fires end up in the same row groups

    display = gdf.copy()
    display[BBOX_COLUMNS] = gdf.geometry.bounds.to_numpy()
    display["geometry"] = display.geometry.simplify(convert_m_4326deg(FIRE_DISPLAY_TOLERANCE_M, 45), preserve_topology=True)

    # write to temporary names then rename, the display file is written last so its presence means the build finished
    for data, path, options in ((gdf, full_path, {"row_group_size": FIRE_ROW_GROUP_SIZE}), (display, display_path, {})):
        tmp_path = path.with_name(path.name + '.tmp')
        data.to_parquet(tmp_path, **options)
        tmp_path.replace(path)





def fx_fire_files_ready(full_path=TOTALFIRE_DATA_PATH, display_path=FIRE_DISPLAY_DATA_PATH):
    #################### ######################################## ######################################## ######################################## ####################
    # True if both fire files exist and line up row for row: same number of rows, and a few sample fires' full detail bounds
    # match the bounds stored in the display copy (catches a full file from a different build, e.g. an unsorted one)
    #################### ######################################## ######################################## ######################################## ####################
    try:
        num_rows = pq.read_metadata(full_path).num_rows
        if num_rows != pq.read_metadata(display_path).num_rows:
            return False
        if num_rows == 0:
            return True
        ids = np.unique(np.linspace(0, num_rows - 1, 5).astype(np.int64))
        stored = pq.read_table(display_path, columns=BBOX_COLUMNS).take(pa.array(ids)).to_pandas().to_numpy()
        actual = fx_read_fire_geometry(ids, full_path).bounds.to_numpy()
        return bool(np.allclose(stored, actual))
    except Exception:                                                                           # missing or unreadable file, or no bbox columns
        return False





def fx_load_fire_display(display_path=FIRE_DISPLAY_DATA_PATH):
    #################### ######################################## ######################################## ######################################## ####################
    # Loads the simplified fire data that stays in memory, its index is each fire's row number in the full detail file
    #################### ######################################## ######################################## ######################################## ####################
    return gpd.read_parquet(display_path)





def fx_read_fire_geometry(ids, full_path=TOTALFIRE_DATA_PATH):
    #################### ######################################## ######################################## ######################################## ####################
    # Reads the full detail geometry for the given row numbers, only reading the row groups that hold them. Returns a GeoSeries indexed by ids
    #################### ######################################## ######################################## ######################################## ####################
    ids = np.asarray(ids, dtype=np.int64)
    parquet = pq.ParquetFile(full_path)
    geo = json.loads(parquet.schema_arrow.metadata[b'geo'])
    crs = geo['columns'][geo['primary_column']].get('crs', 'OGC:CRS84')                        # GeoParquet leaves crs out when it is OGC:CRS84
    if len(ids) == 0:
        return gpd.GeoSeries([], index=ids, crs=crs)

    group_starts = np.cumsum([0] + [parquet.metadata.row_group(i).num_rows for i in range(parquet.num_row_groups)])
    id_groups = np.searchsorted(group_starts, ids, side='right') - 1
    groups = np.unique(id_groups)
    table = parquet.read_row_groups(groups.tolist(), columns=[geo['primary_column']])
    # position of each id inside the table made of only the groups that were read
    group_offsets = np.cumsum([0] + [group_starts[g + 1] - group_starts[g] for g in groups[:-1]])
    positions = group_offsets[np.searchsorted(groups, id_groups)] + ids - group_starts[id_groups]
    wkb = table.column(0).combine_chunks()
    if isinstance(wkb, pa.ExtensionArray):
        wkb = wkb.storage
    return gpd.GeoSeries(shapely.from_wkb(wkb.take(pa.array(positions)).to_numpy(zero_copy_only=False)), index=ids, crs=crs)





def fx_with_full_geometry(gdf, full_path=TOTALFIRE_DATA_PATH):
    #################### ######################################## ######################################## ######################################## ####################
    # Swaps the simplified geometry of filtered fires for their full detail geometry (for exports and fine display tolerances)
    #################### ######################################## ######################################## ######################################## ####################
    gdf = gdf.copy()
    gdf["geometry"] = fx_read_fire_geometry(gdf.index, full_path).to_crs(gdf.crs).values
    return gdf





_fire_data_lock = threading.Lock()

def fx_get_fire_data(download_from_git):
    #################### ######################################## ######################################## ######################################## ####################
    # Makes sure both fire files are on disk. Rebuilds them from an existing full file (older layout or interrupted build),
    # otherwise tries the prebuilt data on Git if download_from_git is True and falls back to downloading and processing from the source
    #################### ######################################## ######################################## ######################################## ####################
    with _fire_data_lock, open(PROCESSED_DATA_FOLDER_PATH / '.fire_data.lock', 'w') as lock_file:   # a second caller (thread or Gunicorn worker) waits here instead of starting a second download
        if fcntl:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
        if fx_fire_files_ready(TOTALFIRE_DATA_PATH, FIRE_DISPLAY_DATA_PATH):
            return

        if TOTALFIRE_DATA_PATH.exists():
            try:
                print(f'...... {timenow()} Rebuilding the Fire Data Files From the Existing Dataset (This May Take Up to 15 Minutes)')
                fx_build_fire_files(gpd.read_parquet(TOTALFIRE_DATA_PATH), TOTALFIRE_DATA_PATH, FIRE_DISPLAY_DATA_PATH)
                return
            except Exception as exc:
                print(f'...... {timenow()} Could Not Rebuild From the Existing Dataset ({exc}), Downloading Again')
                TOTALFIRE_DATA_PATH.unlink(missing_ok=True)

        if download_from_git:
            # Git has both files already built, so nothing needs to be sorted or simplified
            print(f'...... {timenow()} Attempting to Download Fire Data from Git')
            full_ok = download_processed_data(FIRE_DATA_GIT_URL, TOTALFIRE_DATA_PATH.name, PROCESSED_DATA_FOLDER_PATH)
            if full_ok and download_processed_data(FIRE_DISPLAY_GIT_URL, FIRE_DISPLAY_DATA_PATH.name, PROCESSED_DATA_FOLDER_PATH) and fx_fire_files_ready(TOTALFIRE_DATA_PATH, FIRE_DISPLAY_DATA_PATH):
                print(f'......... {timenow()} Download Sucess')
                return
            FIRE_DISPLAY_DATA_PATH.unlink(missing_ok=True)
            if full_ok:
                try:                                                                            # only the full file came through usable, build the display copy from it
                    print(f'......... {timenow()} Could Not Get Both Fire Files from Git, Building Them From the Downloaded Dataset')
                    fx_build_fire_files(gpd.read_parquet(TOTALFIRE_DATA_PATH), TOTALFIRE_DATA_PATH, FIRE_DISPLAY_DATA_PATH)
                    return
                except Exception:
                    TOTALFIRE_DATA_PATH.unlink(missing_ok=True)
            print(f'...... {timenow()} Could Not Get Fire Data from Git, Falling Back to the Source')

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
        print(f'.................. {timenow()} Merging All Fire Data and Building the Fire Data Files')   
        fx_merge_provincial_fires(gdf_qc_fires, gdf_can_fires)





def fx_merge_provincial_fires(data1, data2):
    #################### ######################################## ######################################## ######################################## ####################
    # Merges two datasets
    #################### ######################################## ######################################## ######################################## ####################
    combined_gdf = pd.concat([data1, data2], ignore_index=True)

    combined_gdf = gpd.GeoDataFrame(combined_gdf, geometry='geometry', crs=data1.crs)
    
    fx_build_fire_files(combined_gdf)
    CAN_PROCESSED_DATA_PATH.unlink(missing_ok=True)
    QC_PROCESSED_DATA_PATH.unlink(missing_ok=True)
    return combined_gdf






POLYGON_MAX_BYTES = 10 * 1024 * 1024
def parse_polygon_geojson(document):
    #################### ######################################## ######################################## ######################################## ####################
    # Take in user inputed polygon json, validate it and combine features into one area
    #################### ######################################## ######################################## ######################################## ####################
    
   
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
            # Checks if CRS is not 4326
            if not isinstance(crs, dict) or not isinstance(crs.get("properties"), dict):
                raise ValueError("Boundary coordinates must use EPSG:4326 longitude/latitude.")
            # Checks if CRS is formated properly
            if crs["properties"].get("name") not in {
                "EPSG:4326", "urn:ogc:def:crs:EPSG::4326",
                "urn:ogc:def:crs:OGC:1.3:CRS84", "OGC:CRS84",
            }:
                raise ValueError("Boundary coordinates must use EPSG:4326 longitude/latitude.")
        kind = item.get("type")
        if kind == "FeatureCollection":
            features = item.get("features")
            # Checks if the feature is empty
            if not isinstance(features, list) or not features:
                raise ValueError("Boundary feature collection must not be empty.")
            for feature in features:
                # Makes sure everything in geojson is a feature
                if not isinstance(feature, dict) or feature.get("type") != "Feature":
                    raise ValueError("Feature collections must contain polygon features.")
                read_polygon(feature)
            return
        if kind == "Feature":
            read_polygon(item.get("geometry"))
            return
        # Makes sure the feature is a polygon or multipolygon
        if kind not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Boundary must contain only Polygon or MultiPolygon geometries.")
        # Makes sure geometry column is not empty
        coordinates = item.get("coordinates")
        polygons = [coordinates] if kind == "Polygon" else coordinates
        if not isinstance(polygons, list) or not polygons:
            raise ValueError("Boundary geometry must not be empty.")
        # Verifies polygon rings
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
    #################### ######################################## ######################################## ######################################## ####################
    # Makes sure user inputed number is valid
    #################### ######################################## ######################################## ######################################## ####################
    
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
    fire_data, watershed_data, provincelist,
    min_year=None, max_year=None, min_size=None, max_size=None,
    distance_coords=None, distance_radius=None, watershed_name=None,
    polygon_geojson=None, geometry_source=None,
):
    #################### ######################################## ######################################## ######################################## ####################
    # Applies all user inputed fileters to total_fire dataset and returns the filtered dataset
    # fire_data is the fires in memory. If its geometry is the simplified display copy, pass the full detail file as geometry_source so
    # spatial filters test the exact geometry. The returned fires keep fire_data's geometry, use fx_with_full_geometry for full detail
    #################### ######################################## ######################################## ######################################## ####################
    
    # Makes sure province list is a list of provinces to include
    if not isinstance(provincelist, list) or any(not isinstance(p, str) for p in provincelist):
        raise ValueError("Provinces must be a list of province codes.")
    # Take in year and size inputs
    min_year = filter_number(min_year, "Minimum year", integer=True)
    max_year = filter_number(max_year, "Maximum year", integer=True)
    min_size = filter_number(min_size, "Minimum size")
    max_size = filter_number(max_size, "Maximum size")
    # Makes sure upper bound is not lower than lower bound
    for lower, upper, label in ((min_year, max_year, "year"), (min_size, max_size, "size")):
        if lower is not None and upper is not None and lower > upper:
            raise ValueError(f"Minimum {label} must not exceed maximum {label}.")

    # Take in a verify user inputed coords and radius
    user_point = buffer_deg = watershed_polygon = boundary = None
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

    if watershed_name:
        if not isinstance(watershed_name, str):
            raise ValueError("Watershed name must be text.")
        selected_ws = watershed_data[watershed_data["watershed_name"] == watershed_name.strip()]
        if selected_ws.empty:
            raise ValueError(f'No watershed found with name "{watershed_name}".')
        watershed_polygon = selected_ws.geometry.union_all()

    if polygon_geojson is not None:
        boundary = parse_polygon_geojson(polygon_geojson)

    # Filter based on the province list, fire year and fire size
    filtered_gdf = fire_data if "ALL" in provincelist else fire_data[fire_data["province"].isin(provincelist)]
    for column, lower, upper in (("fire_year", min_year, max_year), ("fire_size", min_size, max_size)):
        if lower is not None:
            filtered_gdf = filtered_gdf[filtered_gdf[column] >= lower]
        if upper is not None:
            filtered_gdf = filtered_gdf[filtered_gdf[column] <= upper]

    # Spatial filters, all in fire_data's crs
    spatial = []                                                                                # (shape, predicate) pairs
    if buffer_deg is not None:
        spatial.append((buffer_deg.to_crs(fire_data.crs).iloc[0], "intersects"))
    if watershed_polygon is not None:
        spatial.append((gpd.GeoSeries([watershed_polygon], crs=watershed_data.crs).to_crs(fire_data.crs).iloc[0], "within"))
    if boundary is not None:
        spatial.append((gpd.GeoSeries([boundary], crs="EPSG:4326").to_crs(fire_data.crs).iloc[0], "intersects"))

    if spatial:
        if geometry_source is not None:
            # fire_data geometry is simplified: narrow down with the exact bounds, then test the full detail geometry of what's left
            bounds = filtered_gdf[BBOX_COLUMNS].to_numpy()
            keep = np.ones(len(filtered_gdf), dtype=bool)
            for shape_, _ in spatial:
                minx, miny, maxx, maxy = shape_.bounds
                keep &= (bounds[:, 0] <= maxx) & (bounds[:, 2] >= minx) & (bounds[:, 1] <= maxy) & (bounds[:, 3] >= miny)
            filtered_gdf = filtered_gdf[keep]
            exact = fx_read_fire_geometry(filtered_gdf.index, geometry_source).to_crs(fire_data.crs)
        else:
            exact = filtered_gdf.geometry
        keep = np.ones(len(filtered_gdf), dtype=bool)
        for shape_, predicate in spatial:
            if predicate == "within":
                keep &= exact.within(shape_).to_numpy()
            else:
                # Query the spatial index to avoid comparing every fire to a complex boundary.
                hits = np.zeros(len(exact), dtype=bool)
                hits[exact.sindex.query(shape_, predicate="intersects")] = True
                keep &= hits
        filtered_gdf = filtered_gdf[keep]

    filtered_gdf = filtered_gdf.drop(columns=BBOX_COLUMNS, errors="ignore")

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