vt_road_surface_tags.py
=======================

Currently this script generates a visualization on road surface tag changes. Soon it will learn how to create an OpenStreetMap import document that can be used to apply tags to ways.

About & License
---------------
Author: Adam Franco  
https://github.com/adamfranco/vt_road_surface_tags 
Copyright 2012 Adam Franco  
License: GNU General Public License Version 3 or later

Usage
=====
This script works with Open Street Map (OSM) XML data files. While you can export these from a
small area directly from [openstreetmap.org](http://www.openstreetmap.org/) , you are limited to a
small area with a limited number of points so that you don't overwhelm the OSM system. A better
alternative is to download daily exports of OSM data for your region from
[Planet.osm](https://wiki.openstreetmap.org/wiki/Planet.osm).

This script was developed using downloads of the US state OSM data provided at:
[download.geofabrik.de/openstreetmap](http://download.geofabrik.de/openstreetmap/north-america/us/)

You will also need to download and unzip the TransRoad_RDS shapefile from [VCGI.org](http://www.vcgi.org/dataware/?page=./search_tools/search_action.cfm&query=theme&theme=018-0025&layers_startrow=21)

Once you have downloaded a .osm file and shapefile that you wish to work with, you can run curvature.py with its
default options:

<code>./vt_road_surface_tags.py -v vermont.osm TransRoad_RDS/Trans_RDS_line.shp</code>

This will generate a vermont.surfaces.kml file that visualizes the tag changes.

Use

<code>./curvature.py -h</code>

for more options.

