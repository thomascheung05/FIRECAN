FireCan is a webmap that allows user to filter and display historic forest fire data.
FireCan uses data from Donne Quebec as well as the Canadian Wildland Fire Information System
FircCan processes data in python, then using a flask sends the polygon data to the java script where it gets mapped by leaflet  

To run FireCan, ensure all dependencies are installed, and run "python firecan_main.py"
FireCan will first install the necessary data (≈2gb) will be downloaded and processed 
The data preperation should take about 10 minutes (majority is downloading the data) and FireCan will  save the data for later use 
Once the app is running, open your local host 

For more information about FireCan see the about section

When running locally, to disable request size limit, change the MAX_SIZE_MB variable on the very first line of firecan_main.py
