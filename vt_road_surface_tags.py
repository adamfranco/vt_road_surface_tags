#!/usr/bin/env python

import os
from datetime import datetime
import shapefile
import argparse
import pyproj
from imposm.parser import OSMParser
import sys
from curvature.collector import WayCollector
import re
import string
from curvature.output import SurfaceKmlOutput
from curvature.filter import WayFilter
from xml.sax.saxutils import escape

parser = argparse.ArgumentParser(description='Extract road surface tags from a shapefile.')
parser.add_argument('-v', action='store_true', help='Verbose mode, showing status output')
parser.add_argument('--output_path', type=str, default='.', help='The path under which output files should be written')
parser.add_argument('--output_basename', type=str, default=None, help='The base of the name for output files. This will be appended with a suffix and extension')
parser.add_argument('osm', type=argparse.FileType('r'), help='The osm file that contains the roads to investigate.')
parser.add_argument('shp', type=argparse.FileType('r'), help='The shapefile that contains the road surface data.')
args = parser.parse_args()

# simple class that handles the parsed OSM data.
class SurfaceWayCollector(WayCollector):
	surface_names = {
		0:'undefined',
		1:'Hard surface (pavement)',
		2:'Gravel',
		3:'Soil or graded and drained earth',
		4:'undefined',
		5:'Unimproved/Primitive',
		6:'Impassable or untravelled',
		7:'undefined',
		8:'undefined',
		9:'Unknown surface type'
	}
	num_surfaces_matched = 0
	num_surfaces_not_found = 0
	num_surfaces_mixed = 0
	
	def __init__(self, proj, sf):
		self.proj = proj
		self.sf = sf
		if self.verbose:
			sys.stderr.write("Loading shapefile...\n")
		self.shapeRecords = sf.shapeRecords()
		
		self.route_rec = None
		self.name_rec = None
		self.surface_rec = None
		for i, field in enumerate(sf.fields):
			if field[0] == 'RTNAME':
				self.route_rec = i - 1
			elif field[0] == 'RDFLNAME':
				self.name_rec = i - 1 
			elif field[0] == 'SURFACE':
				self.surface_rec = i - 1
		
		self.ignored_surfaces = ()

	def add_suffix_variations(self, names, name):
		name = name.strip()
		names.add(name)
		if re.search(' ROAD$', name):
			names.add(re.sub(' ROAD$', ' RD', name))
		if re.search(' PARK$', name):
			names.add(re.sub(' PARK$', ' PK', name))
		if re.search(' PLACE$', name):
			names.add(re.sub(' PLACE$', ' PL', name))
		if re.search(' CIRCLE$', name):
			names.add(re.sub(' CIRCLE$', ' CIR', name))
			names.add(re.sub(' CIRCLE$', ' CR', name))
			names.add(re.sub(' CIRCLE$', ' CL', name))
		if re.search(' TURNPIKE$', name):
			names.add(re.sub(' TURNPIKE$', ' TPKE', name))
			names.add(re.sub(' TURNPIKE$', ' TRNPK', name))
		if re.search(' TPKE$', name):
			names.add(re.sub(' TPKE$', ' TURNPIKE', name))
			names.add(re.sub(' TPKE$', ' TRNPK', name))
		if re.search(' COURT$', name):
			names.add(re.sub(' COURT$', ' CT', name))
		if re.search(' DRIVE$', name):
			names.add(re.sub(' DRIVE$', ' DR', name))
		if re.search(' LANE$', name):
			names.add(re.sub(' LANE$', ' LN', name))
		if re.search(' STREET$', name):
			names.add(re.sub(' STREET$', ' ST', name))
		if re.search(' STREET$', name):
			names.add(re.sub(' STREET$', ' ST', name))
		if re.search(' LANDING$', name):
			names.add(re.sub(' LANDING$', ' LNDG', name))
		if re.search(' WAY$', name):
			names.add(re.sub(' WAY$', ' WY', name))
		if re.search(' AVE$', name):
			names.add(re.sub(' AVE$', ' AV', name))
		if re.search(' AVENUE$', name):
			names.add(re.sub(' AVENUE$', ' AVE', name))
			names.add(re.sub(' AVENUE$', ' AV', name))
		if re.search('TER$', name):
			names.add(re.sub('TER$', 'TERR', name))
		if re.search(' PVT$', name):
			names.add(re.sub(' PVT$', '', name))
		if re.search(' DEAD END$', name):
			names.add(re.sub(' DEAD END$', '', name))
	
	
	def add_segments(self, way):
		way['distance'] = 0.0
		way['curvature'] = 0.0
		way['length'] = 0.0
		second = 0
		third = 0
		segments = []
		for ref in way['refs']:
			first = self.coords[ref]
			
			if not second:
				second = first
				continue			
			if not third:
				third = second
				second = first
				continue
						
			if not len(segments):
				# Add the first segment using the first point
				segments.append({'start': third, 'end': second, 'length': 0, 'radius': 0})
			# Add our latest segment
			segments.append({'start': second, 'end': first, 'length': 0, 'radius': 0})
			
			third = second
			second = first
		
		# Special case for two-coordinate ways
		if len(way['refs']) == 2:
			segments.append({'start': self.coords[way['refs'][0]], 'end': self.coords[way['refs'][1]], 'length': 0, 'radius': 100000})
			
		way['segments'] = segments
		
	def calculate_way(self, way):
		self.add_segments(way)
		
		candidates = []
		names = {way['name'].upper()}
		name = string.join(way['name'].strip().split()).upper()
		self.add_suffix_variations(names, name)
		if re.search(' \(.+\)$', name): # Xxxx Highway (US 7)
			self.add_suffix_variations(names, re.sub(' \(.+\)', '', name))
		if re.search(' DEAD END$', name):
			self.add_suffix_variations(names, re.sub(' DEAD END$', '', name))
		if re.search(' HILL$', name): # Hill roads are sometimes missing 'RD'
			self.add_suffix_variations(names, name + ' RD')
		if re.search('^PVT ', name):
			self.add_suffix_variations(names, re.sub('^PVT ', '', name))
		if re.search('^SAINT ', name):
			self.add_suffix_variations(names, re.sub('^SAINT ', 'ST ', name))
		if re.search('^SOUTH ', name):
			self.add_suffix_variations(names, re.sub('^SOUTH ', 'S ', name))
		if re.search('^NORTH ', name):
			self.add_suffix_variations(names, re.sub('^NORTH ', 'N ', name))
		if re.search('^EAST ', name):
			self.add_suffix_variations(names, re.sub('^EAST ', 'E ', name))
		if re.search('^WEST ', name):
			self.add_suffix_variations(names, re.sub('^WEST ', 'W ', name))
		if re.search('^[NSEW] ', name):
			self.add_suffix_variations(names, re.sub('^([NSEW]) (.+)$', '\g<2> \g<1>', name))
		if re.search(' [NSEW]$', name):
			self.add_suffix_variations(names, re.sub('^(.+) ([NSEW])$', '\g<2> \g<1>', name))
		if re.search('MTN ', name):
			self.add_suffix_variations(names, re.sub('MTN ', 'MOUNTAIN ', name))
		if re.search('MOUNTAIN ', name):
			self.add_suffix_variations(names, re.sub('MOUNTAIN ', 'MTN ', name))
		if re.search('^TOWN (HWY|HIGHWAY) ([0-9]+)', name):
			self.add_suffix_variations(names, re.sub('TOWN (HWY|HIGHWAY) ', 'TH-', name))
		
		if re.search('^STATE ROUTE ', name):
			names.add(re.sub('^STATE ROUTE ', 'VT ', name))
			names.add(re.sub('^STATE ROUTE ', 'VT-', name))
		
		if way['ref']:
			ref_parts = way['ref'].upper().split(';')
			for ref_part in ref_parts:
				names.add(ref_part)
				names.add(ref_part.replace(' ', '-'))
			
		if way['tiger:name_base']:
			names.add(way['tiger:name_base'].upper() + ' ' + way['tiger:name_type'].upper())
		
# 		print 'OSMID: {}\tOSM Name: {}'.format(way['id'], way['name'])
# 		print names
		
		start = self.coords[way['refs'][0]]
		bbox = [start[0], start[1], start[0], start[1]]
		for ref in way['refs']:
			coord = self.coords[ref]
			# lat
			if coord[0] < bbox[0]:
				bbox[0] = coord[0]
			elif coord[0] > bbox[2]:
				bbox[2] = coord[0]
			# lon
			if coord[1] < bbox[1]:
				bbox[1] = coord[1]
			elif coord[1] > bbox[3]:
				bbox[3] = coord[1]
		
		bbox_tl = self.proj(bbox[1], bbox[0])
		bbox_br = self.proj(bbox[3], bbox[2])
		bbox = [bbox_tl[0], bbox_tl[1], bbox_br[0], bbox_br[1]]
		
		for shapeRec in self.shapeRecords:
			name = shapeRec.record[self.name_rec]
			route = shapeRec.record[self.route_rec]
			if name in names or route in names:
				bbox_difference = 0
				for i in range(4):
					bbox_difference = bbox_difference + abs(bbox[i] - shapeRec.shape.bbox[i])
				
				if bbox_difference < 10000:
					candidates.append({'shapeRec':shapeRec, 'bbox_difference':bbox_difference})
		
		if len(candidates):
			candidates = sorted(candidates, key=lambda k: k['bbox_difference'])
			way['shp_surface_matches'] = ''			
			
			if candidates[0]['bbox_difference'] < 8000:
				way['shp_surfaces_match'] = True
				way['shp_surface'] = candidates[0]['shapeRec'].record[self.surface_rec]
			else:
				way['shp_surfaces_match'] = False
				way['shp_surface'] = ''
				
			# ignore any candidates that are twice as bad of a bbox match as our best candidate.
			cutoff = min(2 * candidates[0]['bbox_difference'], 8000)
		
			for candidate in candidates:
				shapeRec = candidate['shapeRec']
				
				way['shp_surface_matches'] += '<hr/><p>Route: {} <br/>\nName: {} <br/>\nSurface: {} - {} <br/>\nDifference: {}</p>\n'.format(shapeRec.record[self.route_rec], escape(shapeRec.record[self.name_rec]), shapeRec.record[self.surface_rec], self.surface_names[shapeRec.record[self.surface_rec]], candidate['bbox_difference'])
				
				if candidate['bbox_difference'] < cutoff and shapeRec.record[self.surface_rec] != way['shp_surface']:
					way['shp_surfaces_match'] = False
						
			
			if way['shp_surfaces_match']:
				self.num_surfaces_matched += 1
			else:
				self.num_surfaces_mixed += 1
			
		else:
			way['shp_surface_matches'] = ''
			way['shp_surface'] = None
			way['shp_surfaces_match'] = None
			self.num_surfaces_not_found += 1
			
class NewSurfaceKmlOutput(SurfaceKmlOutput):
	surface_names = {
		0:'undefined',
		1:'Hard surface (pavement)',
		2:'Gravel',
		3:'Soil or graded and drained earth',
		4:'undefined',
		5:'Unimproved/Primitive',
		6:'Impassable or untravelled',
		7:'undefined',
		8:'undefined',
		9:'Unknown surface type'
	}
	
	def filter_and_sort(self, ways):
		return ways
	
	def get_description(self, way):
		description = '<p>Type: %s<br/>\nExisting Surface: %s<br/>\n' % (way['type'], way['surface'])
		description += '<a href="http://www.openstreetmap.org/browse/way/{}">OSM Details</a></p>\n'.format(way['id'])
		
		description += "<hr/><p>Surface from Shapefile: <br/>  "
		if way['shp_surface']:
			if not way['shp_surfaces_match']:
				description += 'surfaces are mixed, skipping\n'
			else:
				description += '{} -  {}\n'.format(way['shp_surface'], self.surface_names[way['shp_surface']])
		else:
			description += 'no objects matched\n'
		description += "</p>"
		
		description += "\n" + way['shp_surface_matches']
		return description

	def get_styles(self):
		return {
			'notfound':{'color':'F0FFFFFF'},
			'mixed':{'color':'F0AAAAAA'},
			'unknown':{'color':'F0000000'},
			'undefined':{'color':'F0AAAAFF'},
			
			'paved':{'color':'F0FF0000'},
			'unpaved':{'color':'F000FFFF'},
			'gravel':{'color':'F000AAFF'},
			'dirt':{'color':'F06780E5'},#E58067
			'grass':{'color':'F000FF00'},
			'impassable':{'color':'F00000FF'},

		}
	def line_style(self, way):
		if way['shp_surface']:
			if not way['shp_surfaces_match']:
				return 'mixed'
			elif way['shp_surface'] == 1:
				return 'paved'
			elif way['shp_surface'] == 2:
				return 'gravel'
			elif way['shp_surface'] == 3:
				return 'dirt'
			elif way['shp_surface'] == 5:
				return 'grass'
			elif way['shp_surface'] == 6:
				return 'impassable'
			elif way['shp_surface'] == 9:
				return 'unknown'
			else:
				return 'undefined'
		else:
			return 'notfound'
	
	def _write_doc_start(self, f):
		super(NewSurfaceKmlOutput, self)._write_doc_start(f)
		f.write('	<ScreenOverlay>\n')
		f.write('		<name>Legend</name>\n')
		f.write('		<Icon><href>http://www2.adamfranco.com/surface/SurfaceLegend.jpg</href></Icon>\n')
		f.write('		<overlayXY x="1" y="0.5" xunits="fraction" yunits="fraction"/>\n')
		f.write('		<screenXY x="1" y="0.5" xunits="fraction" yunits="fraction"/>\n')
		f.write('		<rotationXY x="0" y="0" xunits="fraction" yunits="fraction"/>\n')
		f.write('		<size x="0" y="0" xunits="fraction" yunits="fraction"/>\n')
		f.write('	</ScreenOverlay>\n')

p = pyproj.Proj(r'+proj=tmerc +lat_0=42.5 +lon_0=-72.5 +k=0.999964286 +x_0=500000 +y_0=0 +ellps=GRS80 +datum=NAD83 +units=m +no_defs') # State Plane Coordinate System 1983
sf = shapefile.Reader(args.shp.name)

collector = SurfaceWayCollector(p, sf)
collector.verbose = args.v
start = datetime.now()
collector.load_file(args.osm.name)
end = datetime.now()

# Generate KML output
if args.v:
	sys.stderr.write("Calculation completed in {}\n".format(end - start))
	sys.stderr.write("generating KML output\n")

if args.output_path is None:
	path = os.path.dirname()
else:
	path = args.output_path
if args.output_basename is None:
	basename = os.path.basename(args.osm.name)
	parts = os.path.splitext(basename)
	basename = parts[0]
else:
	basename = os.path.basename(args.output_basename)
	
kml = NewSurfaceKmlOutput(WayFilter())
kml.write(collector.ways, path, basename)

if args.v:
	sys.stderr.write("done.\n")

print "Ways with surfaces matched:   {:6d}".format(collector.num_surfaces_matched)
print "Ways with surfaces mixed:     {:6d}".format(collector.num_surfaces_mixed)
print "Ways with surfaces not found: {:6d}".format(collector.num_surfaces_not_found)
