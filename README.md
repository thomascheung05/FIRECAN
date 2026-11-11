# FIRECAN

FIRECAN is a web-based mapping application that enables users to filter and visualize historical forest fire data across Canada. It processes and serves fire data from Donnees Quebec and the Canadian Wildland Fire Information System (CWFIS), allowing for dynamic exploration on an interactive map.

The backend is built with Python using Flask and GeoPandas for data processing, while the frontend uses Leaflet.js to render geographic data and provide an interactive user experience. 

## Features

*   **Interactive Map**: A full-window map with a collapsible floating filter panel and multiple base layers (e.g., Esri Imagery, OpenStreetMap).
*   **Comprehensive Filtering**:
    *   Filter fires by province or select all.
    *   Specify a date range (minimum/maximum year).
    *   Filter by fire size in hectares (min/max).
    *   Isolate fires within a specific radius of a coordinate point.
    *   Select fires contained within a specific Quebec watershed.
    *   Upload your own GeoJSON boundary to select fires that overlap or touch it.
*   **Polygon Resolution Tuning**: Adjust the polygon tolerance to increase polygon resolution and gain more detail.
*   **Data Export**: Download your filtered dataset in various formats, including GeoJSON, CSV, and GPKG.
*   **Watershed Explorer**: An interactive map tool to find and select Quebec watersheds for filtering.
*   **Custom Polygon Filtering**: Upload a custom polygon to filter by. 

## Data Sources

FIRECAN utilizes publicly available data from the following sources:

*   **Quebec Fires**: [Données Québec - Feux de forêt](https://www.donneesquebec.ca/recherche/dataset/feux-de-foret)
*   **Watersheds**: [Esri Canada Education and Research](https://hub.arcgis.com/maps/12b6e33d5a754c92b97ae5d0fed6940a/about)
*   **All Other Provinces**: [Canadian Wildland Fire Information System (CWFIS)](https://cwfis.cfs.nrcan.gc.ca/datamart)

<br>
<br>
<br>
<br>

# FIRECAN Very In Depth Install Guide

## Step 0: Support
If anything in this guide is unclear or something is not working or something goes wrong. PLEASE contact me here: thomascheung48@gmail.com
I really want YOU to use FIRECAN, so if anything goes wrong don't hesitate to reach out. I would rather spend 10 hours helping you run the software then not have the software run.
Thanks! -Tom

## Step 1: Installing Python 
- There are many tutorials on how to install python, whichever one works.
	* [Windows Python Install](https://www.youtube.com/watch?v=C3bOxcILGu4) 
	* [Mac Python Install](https://www.youtube.com/watch?v=VJjeMdl6yWA)
- If on PC make sure to check the "ADD TO PATH" box during the install wizard
- If on MAC run "python3" instead of "python" in your terminal to run python
- After python is installed, ignore all the files it downloaded and instead open your Terminal (Mac) or Command Prompt (Windows)
- Type in "Python3 --version" (Mac) or "Python --version" (Windows)
- If it prints out your python version you're all set!
``` bash
tom@thomass-MacBook-Pro ~ % python3 --version
Python 3.14.7
```

## Step 2: Download the scripts
1) Go to the Git Hub (https://github.com/thomascheung05/FIRECAN)
2) In the toolbar on the right, click on "releases"
	![[firecanreleasesss.png|281]]
3) Under FIRECAN_betaV1 click on "Source Code (zip)" and it will download automatically
	![[firecanreleasesdownloadzipss.png|293]]
4) No need to download any data from the Github, the script will do this for you

## Step 3: Running the code
- Unzip the "FIRECAN-beta.zip" and open the unzipped folder
### Mac:
1) Open your terminal
2) Type "bash " but do not press enter (ensure there is a space after "bash")
3) Drag and drop the "FIRECAN.sh" file into the terminal
4) Hit enter - This will run FIRECAN. The first run, it must download the data which can take up to 15 minutes for raw data, every subsequent run should only take 2 minutes to boot up. Once the app is booted it will automatically open your browser and it's ready to go
### Windows:
1) Windows does not have "bash" so we will have to run FIRECAN directly through python. This is the standard way to run a python script and also works on Mac if "bash"is not working 
2) In the "FIRECAN-beta" right click any file and click "properties"
3) Under the "General" Tab look for the row that says "Location:" the following text is the path to the "FIRECAN-beta" folder. It should look something like this: /c/Users/Tom/Downloads/FIRECAN-beta
4) Open cmd and run the following command "cd your/path/to/the/FIRECAN-betafolder". Now, you have the FIRECAN-beta folder open in your terminal
5) Run these commands (one at at time works best) to start FIRECAN. Refer back to step 5
#### First Time Setup
```bash
python -m venv .venv
 
source .venv/Scripts/activate 

python -m pip install requirements.txt 

python app/firecan_main.py
```
#### All Subsequent Runs After The First 
```bash
source .venv/Scripts/activate 

python app/firecan_main.py
```

## Configuration

### File Size Cap
Large map results and geometry exports have a 200 MB response limit. To adjust this, you can change the `MAX_SIZE_MB` variable at the top of the `app/firecan_main.py` file.

```python
# firecan_main.py
MAX_SIZE_MB = 200 # Change this value as needed
```

### Download Data from git
By default, the pre-processed data is downloaded from the FIRECAN github repository. If you want to download the unprocessed data, change `DOWNLOAD_FROM_GIT` to False.

```python
# firecan_main.py
DOWNLOAD_FROM_GIT = False
```











  