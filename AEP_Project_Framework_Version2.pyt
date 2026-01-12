# -*- coding: utf-8 -*-
"""
ArcGIS Pro Project Framework Toolbox
For environmental assessment projects in New South Wales, Australia
Requires ArcGIS Pro 3.6 or greater
"""

import arcpy
import os
import json
import urllib.request
import urllib.parse

# Global Path to Layer File (Standard Styling)
LAYERFILE_PATH = r"G:\Shared drives\99.3 GIS Admin\Production\Layer Files\AEP - Study Area.lyrx"


class Toolbox(object):
    def __init__(self):
        self.label = "AEP Project Framework Toolbox"
        self.alias = "AEPFramework"
        self.tools = [CreateSubjectSite, AddStandardProjectLayers]


class CreateSubjectSite(object):
    def __init__(self):
        self.label = "Step 1 - Create Subject Site"
        self.description = "Creates a standardized subject site polygon from an NSW address and writes it to the feature service"
        self.canRunInBackground = False

    def getParameterInfo(self):
        # Param 0: User types freely here (Search Box)
        param0 = arcpy.Parameter(
            displayName="Address Search (Type and press Tab)",
            name="search_text",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        
        # Param 1: Dropdown populates based on search (Selection Box)
        param1 = arcpy.Parameter(
            displayName="Select Exact Address",
            name="site_address",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param1.filter.type = "ValueList"
        param1.filter.list = []

        param2 = arcpy.Parameter(
            displayName="Project Number",
            name="project_number",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param2.value = "6666"

        param3 = arcpy.Parameter(
            displayName="Project Name",
            name="project_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param3.value = "Devil's Pinch"

        param4 = arcpy.Parameter(
            displayName="Output Study Area",
            name="output_fc",
            datatype="GPString",
            parameterType="Derived",
            direction="Output")

        return [param0, param1, param2, param3, param4]

    def isLicensed(self):
        return True

    def _get_token(self):
        try:
            info = arcpy.GetSigninToken()
            return info.get("token") if info else None
        except:
            return None

    def _get_suggestions(self, text, token):
        # Helper to query the API for suggestions
        base = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/suggest"
        params = {"text": text, "f": "json", "maxSuggestions": 10, "countryCode": "AUS"}
        if token:
            params["token"] = token
        
        try:
            url = f"{base}?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            
            if "suggestions" in data:
                return [s["text"] for s in data["suggestions"]]
            return []
        except Exception:
            return []

    def updateParameters(self, parameters):
        # Unpack parameters for clarity
        p_search = parameters[0]
        p_select = parameters[1]

        # Logic: If the user changed the "Search" text, update the "Select" dropdown
        if p_search.altered and p_search.valueAsText:
            # Only search if text is longer than 3 chars to save API calls
            if len(p_search.valueAsText) > 3:
                # Check if we haven't already populated this list for the same text
                token = self._get_token()
                suggestions = self._get_suggestions(p_search.valueAsText, token)
                
                if suggestions:
                    p_select.filter.list = suggestions
                    # Auto-select the first option to be helpful
                    if not p_select.valueAsText:
                        p_select.value = suggestions[0]
                else:
                    p_select.filter.list = []
        return

    def updateMessages(self, parameters):
        p_select = parameters[1]
        p_proj_num = parameters[2]
        p_proj_name = parameters[3]

        if not p_select.valueAsText:
            p_select.setErrorMessage("You must select an address from the dropdown list.")

        if p_proj_num.altered:
            val = p_proj_num.valueAsText
            if val and (not val.isdigit() or len(val) > 5):
                p_proj_num.setErrorMessage("Project Number must be 5 digits or less (numeric).")

        if p_proj_name.altered:
            val = p_proj_name.valueAsText
            if val and len(val) > 150:
                p_proj_name.setErrorMessage("Project Name too long (>150 chars).")
        return

    def execute(self, parameters, messages):
        # We use param[1] (The Selected Address) for the actual processing
        site_address = parameters[1].valueAsText 
        project_number = parameters[2].valueAsText
        project_name = parameters[3].valueAsText

        target_layer_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"

        arcpy.AddMessage("=" * 60)
        arcpy.AddMessage("STEP 1 - CREATE SUBJECT SITE")
        arcpy.AddMessage("=" * 60)

        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            default_gdb = aprx.defaultGeodatabase
            arcpy.env.workspace = default_gdb

            # 1. Geocode
            token = self._get_token()
            base_url = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            
            params = {
                'SingleLine': site_address, 
                'f': 'json', 
                'outSR': '4326', 
                'maxLocations': 1,
                'countryCode': 'AUS' 
            }
            if token:
                params['token'] = token
            
            url = f"{base_url}?{urllib.parse.urlencode(params)}"

            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode())

            if not data.get('candidates'):
                arcpy.AddError(f"Could not locate coordinate for address: {site_address}")
                return

            candidate = data['candidates'][0]
            matched_address = candidate['address']
            loc = candidate['location']
            
            # Create point
            geocoded_point = arcpy.PointGeometry(arcpy.Point(loc['x'], loc['y']), arcpy.SpatialReference(4326))
            temp_geocoded = os.path.join("memory", "geocoded_point")
            arcpy.management.CopyFeatures(geocoded_point, temp_geocoded)
            
            arcpy.AddMessage(f"Located at: {loc['x']:.5f}, {loc['y']:.5f}")

            # 2. Select property polygon (Cadastre)
            property_service_url = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer/12"
            
            temp_property_layer = "temp_property_layer"
            arcpy.management.MakeFeatureLayer(property_service_url, temp_property_layer)
            
            arcpy.AddMessage("Selecting property parcel...")
            arcpy.management.SelectLayerByLocation(temp_property_layer, "CONTAINS", temp_geocoded)
            
            property_count = int(arcpy.management.GetCount(temp_property_layer).getOutput(0))
            if property_count == 0:
                arcpy.AddError("No property polygon found at this location (NSW Cadastre).")
                return

            # Copy selection to local GDB
            temp_property = os.path.join(default_gdb, "temp_property")
            if arcpy.Exists(temp_property):
                arcpy.management.Delete(temp_property)
                
            arcpy.management.CopyFeatures(temp_property_layer, temp_property)
            arcpy.management.Delete(temp_property_layer)
            arcpy.management.Delete(temp_geocoded)

            arcpy.management.RepairGeometry(temp_property, "DELETE_NULL")

            # Handle multi-polygon properties
            if property_count > 1:
                dissolved = os.path.join(default_gdb, "temp_dissolved")
                if arcpy.Exists(dissolved): arcpy.management.Delete(dissolved)
                arcpy.management.Dissolve(temp_property, dissolved, multi_part="MULTI_PART")
                working_fc = dissolved
            else:
                working_fc = temp_property

            # 3. Add & Calculate Attributes
            arcpy.AddMessage("Preparing attributes...")
            target_fields = [
                ("project_number", "TEXT", 256),
                ("ProjectName", "TEXT", 150),
                ("GeocodedAddress", "TEXT", 255),
                ("SiteArea", "DOUBLE", None),
                ("AreaUnits", "TEXT", 20),
                ("Area_ha", "DOUBLE", None),
                ("Comments", "TEXT", 255)
            ]
            
            for fname, ftype, flen in target_fields:
                if not arcpy.ListFields(working_fc, fname):
                    if ftype == "TEXT":
                        arcpy.management.AddField(working_fc, fname, ftype, field_length=flen)
                    else:
                        arcpy.management.AddField(working_fc, fname, ftype)

            with arcpy.da.UpdateCursor(working_fc, ["SHAPE@", "project_number", "ProjectName", "GeocodedAddress", "SiteArea", "AreaUnits", "Area_ha"]) as cursor:
                for row in cursor:
                    area_sqm = row[0].getArea("GEODESIC", "SQUAREMETERS")
                    area_ha = area_sqm / 10000.0
                    area_units = "hectares" if area_sqm > 10000 else "square meters"
                    
                    row[1] = project_number
                    row[2] = project_name
                    row[3] = matched_address
                    row[4] = area_ha if area_units == "hectares" else area_sqm
                    row[5] = area_units
                    row[6] = area_ha
                    cursor.updateRow(row)

            arcpy.AddMessage(f"  ✓ Site area: {area_ha:.2f} hectares")

            # 4. Append to Feature Service
            arcpy.AddMessage("Writing to feature service...")
            arcpy.management.Append(working_fc, target_layer_url, "NO_TEST")

            # 5. Clean up
            if arcpy.Exists(temp_property): arcpy.management.Delete(temp_property)
            if property_count > 1 and arcpy.Exists(dissolved): arcpy.management.Delete(dissolved)

            # 6. Add to Map (No Zoom)
            try:
                map_obj = aprx.activeMap
                if map_obj and os.path.exists(LAYERFILE_PATH):
                    arcpy.AddMessage(f"Adding styled layer from: {LAYERFILE_PATH}")
                    lyr_file = arcpy.mp.LayerFile(LAYERFILE_PATH)
                    added_layers = map_obj.addLayer(lyr_file)
                    
                    if added_layers:
                        target_lyr = added_layers[0]
                        target_lyr.name = f"Project Study Area {project_number}"
                        
                        if target_lyr.supports("DEFINITIONQUERY"):
                            dq = f"project_number = '{project_number}' AND EndDate IS Not Null"
                            target_lyr.definitionQuery = dq
                            arcpy.AddMessage(f"✓ Layer renamed and filtered to project {project_number} AND EndDate IS Not Null")
                else:
                    arcpy.AddWarning("Map or Layer File not found. Layer not added to map.")
            except Exception as e:
                arcpy.AddWarning(f"Could not update map: {str(e)}")

            arcpy.AddMessage("\nSUCCESS!")

        except Exception as e:
            arcpy.AddError(f"\n✗ Error: {str(e)}")
            import traceback
            arcpy.AddError(traceback.format_exc())
        return


class AddStandardProjectLayers(object):
    def __init__(self):
        self.label = "Step 2 - Add Standard Project Layers"
        self.description = "Adds standard project layers based on the subject site"
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Project Number (choose Study Area)",
            name="project_number_choice",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param0.filter.list = []
        param0.value = "6666"
        return [param0]

    def isLicensed(self):
        return True

    def _get_token(self):
        try:
            info = arcpy.GetSigninToken()
            return info.get("token") if info else None
        except:
            return None

    def _get_unique_project_numbers(self, target_layer_url, token):
        params = {"where": "1=1", "outFields": "project_number", "returnDistinctValues": "true", "f": "json"}
        if token: params["token"] = token
        query_url = f"{target_layer_url}/query?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(query_url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return sorted([feat['attributes']['project_number'] for feat in data.get('features', []) if feat['attributes']['project_number']])

    def _get_study_area_by_project_number(self, target_layer_url, token, project_number):
        where = f"project_number='{project_number}'".replace("'", "''")
        params = {"where": where, "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json"}
        if token: params["token"] = token
        query_url = f"{target_layer_url}/query?{urllib.parse.urlencode(params)}"
        
        with urllib.request.urlopen(query_url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        
        if not data['features']:
            return None

        feat = data['features'][0]
        sr = data.get('spatialReference') or {"wkid": 4326}
        polygon = arcpy.AsShape({"rings": feat['geometry']['rings'], "spatialReference": sr}, True)
        
        temp_fc = os.path.join("memory", f"study_area_{project_number}")
        arcpy.management.CopyFeatures(polygon, temp_fc)
        
        # Add basic attributes back (simplified)
        for fname, fval in feat['attributes'].items():
            if fname not in ("OBJECTID", "GlobalID", "Shape", "Shape_Area", "Shape_Length"):
                try: 
                    arcpy.management.AddField(temp_fc, fname, "TEXT", field_length=255)
                except: 
                    pass
        
        return temp_fc

    def updateParameters(self, parameters):
        url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"
        try:
            token = self._get_token()
            parameters[0].filter.list = self._get_unique_project_numbers(url, token)
        except: pass
        return

    def execute(self, parameters, messages):
        project_number = parameters[0].valueAsText
        target_layer_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"
        
        arcpy.AddMessage("=" * 60)
        arcpy.AddMessage("STEP 2 - ADD PROJECT LAYERS")
        arcpy.AddMessage("=" * 60)

        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            map_obj = aprx.activeMap
            
            if not map_obj:
                arcpy.AddError("No active map found. Please open a map view.")
                return

            token = self._get_token()
            
            # 1. Retrieve the study area
            arcpy.AddMessage(f"Retrieving study area for Project {project_number}...")
            study_area_fc = self._get_study_area_by_project_number(target_layer_url, token, project_number)
            
            if not study_area_fc:
                arcpy.AddError(f"Could not find study area for Project {project_number}")
                return

            # 2. Add Study Area to Map
            arcpy.AddMessage("Adding Study Area to map...")
            
            layer_name = f"Study Area - {project_number}"
            
            # Check for standard layer file
            if os.path.exists(LAYERFILE_PATH):
                lyr_file = arcpy.mp.LayerFile(LAYERFILE_PATH)
                added_layers = map_obj.addLayer(lyr_file)
                if added_layers:
                    target_lyr = added_layers[0]
                    target_lyr.name = layer_name
                    
                    if target_lyr.supports("DEFINITIONQUERY"):
                        target_lyr.definitionQuery = f"project_number = '{project_number}'"
            else:
                # Fallback: Save to default GDB and add raw
                saved_fc = os.path.join(aprx.defaultGeodatabase, f"StudyArea_{project_number}")
                if arcpy.Exists(saved_fc):
                    arcpy.management.Delete(saved_fc)
                arcpy.management.CopyFeatures(study_area_fc, saved_fc)
                map_obj.addDataFromPath(saved_fc)

            arcpy.AddMessage("\nSUCCESS - Project Layers Added.")

        except Exception as e:
            arcpy.AddError(f"Error executing Step 2: {str(e)}")
            import traceback
            arcpy.AddError(traceback.format_exc())
        return

