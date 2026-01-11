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
from datetime import datetime


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the . pyt file)."""
        self.label = "AEP Project Framework Toolbox"
        self.alias = "AEPFramework"
        self.tools = [CreateSubjectSite, AddStandardProjectLayers]


class CreateSubjectSite(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 1 - Create Subject Site"
        self.description = "Creates a standardized subject site polygon from an NSW address"
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        # Parameter 0: Site Address
        param0 = arcpy.Parameter(
            displayName="Site Address",
            name="site_address",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param0.value = "354 thompsons road, milbrodale"  # Default value
        
        # Parameter 1: Project Number
        param1 = arcpy.Parameter(
            displayName="Project Number",
            name="project_number",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param1.value = "6666"  # Default value
        
        # Parameter 2: Project Name
        param2 = arcpy.Parameter(
            displayName="Project Name",
            name="project_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param2.value = "Devil's Pinch"  # Default value
        
        # Parameter 3: Output Feature Class
        param3 = arcpy.Parameter(
            displayName="Output Study Area",
            name="output_fc",
            datatype="DEFeatureClass",
            parameterType="Derived",
            direction="Output")
        
        params = [param0, param1, param2, param3]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter."""
        # Validate Project Number (max 5 numeric characters)
        if parameters[1].altered:
            proj_num = parameters[1].valueAsText
            if proj_num: 
                if not proj_num.isdigit():
                    parameters[1].setErrorMessage("Project Number must contain only numeric characters")
                elif len(proj_num) > 5:
                    parameters[1].setErrorMessage("Project Number must be 5 characters or less")
        
        # Validate Project Name (max 150 characters)
        if parameters[2].altered:
            proj_name = parameters[2].valueAsText
            if proj_name and len(proj_name) > 150:
                parameters[2].setErrorMessage("Project Name must be 150 characters or less")
        
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        
        # Get parameters
        site_address = parameters[0].valueAsText
        project_number = parameters[1].valueAsText
        project_name = parameters[2].valueAsText
        
        arcpy.AddMessage("="*60)
        arcpy.AddMessage("STEP 1 - CREATE SUBJECT SITE")
        arcpy.AddMessage("="*60)
        arcpy.AddMessage(f"Site Address: {site_address}")
        arcpy.AddMessage(f"Project Number: {project_number}")
        arcpy.AddMessage(f"Project Name: {project_name}")
        arcpy.AddMessage("")
        
        try:
            # Get current project and default geodatabase
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            default_gdb = aprx.defaultGeodatabase
            arcpy.AddMessage(f"Using geodatabase: {default_gdb}\n")
            
            # Set workspace
            arcpy.env.workspace = default_gdb
            
            # Step 1: Geocode the address using Esri World Geocoding Service REST API
            arcpy.AddMessage("Step 1: Geocoding address with Esri World Geocoding Service...")
            
            # Append ", NSW, Australia" to improve geocoding accuracy
            full_address = f"{site_address}, NSW, Australia"
            arcpy.AddMessage(f"  Searching for: {full_address}")
            
            # Get token from ArcGIS Pro
            try:
                token_info = arcpy.GetSigninToken()
                if token_info:
                    token = token_info['token']
                    arcpy.AddMessage("  Using ArcGIS Pro authentication")
                else: 
                    token = None
                    arcpy.AddMessage("  No token available - using unauthenticated request")
            except: 
                token = None
                arcpy.AddMessage("  No token available - using unauthenticated request")
            
            # Build the REST API URL for findAddressCandidates
            base_url = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
            params = {
                'SingleLine': full_address,
                'f': 'json',
                'outSR': '4326',
                'maxLocations': 1
            }
            
            # Add token if available
            if token:
                params['token'] = token
            
            url = f"{base_url}?{urllib.parse.urlencode(params)}"
            
            arcpy.AddMessage("  Calling Esri World Geocoding Service...")
            
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = json.loads(response.read().decode())
                
                # Check for errors
                if 'error' in data:
                    arcpy.AddError(f"Geocoding service error: {data['error']['message']}")
                    if data['error']['code'] == 499:
                        arcpy.AddError("Authentication required. Please ensure you are signed into ArcGIS Pro.")
                    return
                
                # Check if we got results
                if not data or 'candidates' not in data or len(data['candidates']) == 0:
                    arcpy.AddError(f"Could not geocode address: {site_address}")
                    arcpy.AddError("Please check the address format and try again.")
                    return
                
                # Get the best candidate
                candidate = data['candidates'][0]
                matched_address = candidate['address']
                score = candidate['score']
                location = candidate['location']
                location_x = location['x']
                location_y = location['y']
                
                arcpy.AddMessage(f"  ✓ Geocoded to: {matched_address}")
                arcpy.AddMessage(f"  ✓ Match score: {score}")
                arcpy.AddMessage(f"  ✓ Coordinates (WGS84): {location_x:.6f}, {location_y:.6f}")
                
                if score < 80:
                    arcpy.AddWarning(f"  ⚠ Low match score ({score}). Results may not be accurate.")
                
            except urllib.error.HTTPError as http_err:
                arcpy.AddError(f"HTTP error occurred: {http_err}")
                arcpy.AddError(f"Status code: {http_err.code}")
                try:
                    error_body = http_err.read().decode()
                    arcpy.AddError(f"Error details: {error_body}")
                except:
                    pass
                return
            except urllib.error.URLError as url_err:
                arcpy.AddError(f"URL error occurred:  {url_err}")
                arcpy.AddError("Please check your internet connection.")
                return
            except json.JSONDecodeError as json_err:
                arcpy.AddError(f"JSON decode error: {json_err}")
                return
            
            # Create a point geometry from the geocoded location
            geocoded_point = arcpy.PointGeometry(
                arcpy.Point(location_x, location_y),
                arcpy.SpatialReference(4326)
            )
            
            # Save as temporary feature for spatial selection
            temp_geocoded = os.path.join("memory", "geocoded_point")
            arcpy.management.CopyFeatures(geocoded_point, temp_geocoded)
            
            # Step 2: Use the geocoded point to select property polygon
            property_service_url = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer/12"
            
            arcpy.AddMessage("\nStep 2: Querying NSW Land Parcel Property Theme...")
            
            # Create a temporary layer from the property service
            temp_property_layer = "temp_property_layer"
            arcpy.management.MakeFeatureLayer(property_service_url, temp_property_layer)
            
            # Select property polygons that contain the geocoded point
            arcpy.AddMessage("  Selecting property polygon(s) containing geocoded point...")
            arcpy.management.SelectLayerByLocation(
                in_layer=temp_property_layer,
                overlap_type="CONTAINS",
                select_features=temp_geocoded,
                selection_type="NEW_SELECTION"
            )
            
            # Get count of selected properties
            property_result = arcpy.management.GetCount(temp_property_layer)
            property_count = int(property_result.getOutput(0))
            
            if property_count == 0:
                arcpy.AddError(f"No property polygon found at geocoded location")
                arcpy.AddError(f"Coordinates: {location_x:.6f}, {location_y:.6f}")
                arcpy.AddError("The address may be valid but not associated with a property polygon.")
                return
            
            arcpy.AddMessage(f"  ✓ Found {property_count} property polygon(s)")
            
            # Step 3: Copy selected features to a temporary feature class
            temp_property = os.path.join(default_gdb, "temp_property")
            arcpy.management.CopyFeatures(temp_property_layer, temp_property)
            
            # Clean up
            arcpy.management.Delete(temp_property_layer)
            arcpy.management.Delete(temp_geocoded)
            
            # Step 4: Repair geometry
            arcpy.AddMessage("\nStep 3: Repairing geometry...")
            arcpy.management.RepairGeometry(temp_property, "DELETE_NULL")
            arcpy.AddMessage("  ✓ Geometry repaired")
            
            # Step 5:  Dissolve if multiple polygons
            if property_count > 1:
                arcpy.AddMessage("\nStep 4: Dissolving multiple polygons into single feature...")
                dissolved = os.path.join(default_gdb, "temp_dissolved")
                arcpy.management.Dissolve(
                    in_features=temp_property,
                    out_feature_class=dissolved,
                    dissolve_field=None,
                    multi_part="MULTI_PART"
                )
                arcpy.AddMessage("  ✓ Polygons dissolved")
                working_fc = dissolved
            else:
                working_fc = temp_property
            
            # Step 6: Calculate area and determine units
            arcpy.AddMessage("\nStep 5: Calculating area...")
            
            arcpy.management.CalculateGeometryAttributes(
                working_fc,
                [["SHAPE_Area", "AREA_GEODESIC"]],
                area_unit="SQUARE_METERS"
            )
            
            # Get the area value
            with arcpy.da.SearchCursor(working_fc, ["SHAPE@AREA"]) as cursor:
                for row in cursor:
                    area_sqm = row[0]
                    break
            
            # Determine area and units
            if area_sqm > 10000:
                area_value = area_sqm / 10000
                area_units = "hectares"
            else:
                area_value = area_sqm
                area_units = "square meters"
            
            arcpy.AddMessage(f"  ✓ Site area: {area_value:.2f} {area_units}")
            
            # Step 7: Save final output with project attributes
            arcpy.AddMessage("\nStep 6: Creating Project_Study_Area...")
            output_fc = os.path.join(default_gdb, "Project_Study_Area")
            
            if arcpy.Exists(output_fc):
                arcpy.management.Delete(output_fc)
            
            arcpy.management.CopyFeatures(working_fc, output_fc)
            
            # Add custom fields
            arcpy.management.AddField(output_fc, "ProjectNumber", "TEXT", field_length=5)
            arcpy.management.AddField(output_fc, "ProjectName", "TEXT", field_length=150)
            arcpy.management.AddField(output_fc, "SiteAddress", "TEXT", field_length=255)
            arcpy.management.AddField(output_fc, "GeocodedAddress", "TEXT", field_length=255)
            arcpy.management.AddField(output_fc, "GeocodeScore", "SHORT")
            arcpy.management.AddField(output_fc, "Longitude", "DOUBLE")
            arcpy.management.AddField(output_fc, "Latitude", "DOUBLE")
            arcpy.management.AddField(output_fc, "SiteArea", "DOUBLE")
            arcpy.management.AddField(output_fc, "AreaUnits", "TEXT", field_length=50)
            arcpy.management.AddField(output_fc, "CreatedDate", "DATE")
            
            # Populate fields
            with arcpy.da.UpdateCursor(output_fc, 
                ["ProjectNumber", "ProjectName", "SiteAddress", "GeocodedAddress", 
                 "GeocodeScore", "Longitude", "Latitude", "SiteArea", "AreaUnits", "CreatedDate"]) as cursor:
                for row in cursor: 
                    row[0] = project_number
                    row[1] = project_name
                    row[2] = site_address
                    row[3] = matched_address
                    row[4] = score
                    row[5] = location_x
                    row[6] = location_y
                    row[7] = area_value
                    row[8] = area_units
                    row[9] = datetime.now()
                    cursor.updateRow(row)
            
            arcpy.AddMessage("  ✓ Attributes populated")
            
            # Clean up temporary data
            arcpy.management.Delete(temp_property)
            if property_count > 1:
                arcpy.management.Delete(dissolved)
            
            parameters[3].value = output_fc
            
            arcpy.AddMessage("\n" + "="*60)
            arcpy.AddMessage("SUCCESS!")
            arcpy.AddMessage(f"Project Study Area created:  {output_fc}")
            arcpy.AddMessage("="*60)
            
            # Add to current map
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            map_obj = aprx.activeMap
            if map_obj:
                map_obj.addDataFromPath(output_fc)
                arcpy.AddMessage("✓ Layer added to current map")
            
        except Exception as e:
            arcpy.AddError(f"\n✗ Error creating subject site: {str(e)}")
            import traceback
            arcpy.AddError(traceback.format_exc())
        
        return


class AddStandardProjectLayers(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 2 - Add Standard Project Layers"
        self.description = "Adds standard project layers based on the subject site"
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        param0 = arcpy.Parameter(
            displayName="Project Study Area",
            name="study_area",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Polygon"]
        
        params = [param0]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        
        study_area_fc = parameters[0].valueAsText
        
        arcpy.AddMessage("="*60)
        arcpy.AddMessage("STEP 2 - ADD STANDARD PROJECT LAYERS")
        arcpy.AddMessage("="*60)
        
        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            default_gdb = aprx.defaultGeodatabase
            arcpy.env.workspace = default_gdb
            
            reference_table_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15"
            
            arcpy.AddMessage("Querying standard connection reference table...")
            
            temp_table = "temp_reference_table"
            arcpy.management.MakeTableView(reference_table_url, temp_table)
            
            reference_records = []
            fields = ["URL", "SiteBuffer", "BufferAction", "FeatureDatasetName", "LayerName"]
            
            with arcpy.da.SearchCursor(temp_table, fields) as cursor:
                for row in cursor:
                    reference_records.append({
                        "url": row[0],
                        "buffer_distance": row[1],
                        "buffer_action": row[2],
                        "feature_dataset": row[3],
                        "layer_name": row[4]
                    })
            
            arcpy.AddMessage(f"Found {len(reference_records)} layers to process\n")
            
            map_obj = aprx.activeMap
            
            for idx, record in enumerate(reference_records, 1):
                try:
                    arcpy.AddMessage(f"[{idx}/{len(reference_records)}] Processing: {record['layer_name']}")
                    arcpy.AddMessage("-" * 60)
                    
                    buffer_distance = record['buffer_distance']
                    arcpy.AddMessage(f"  Buffering site by {buffer_distance} meters...")
                    
                    temp_buffer = os.path.join("memory", f"buffer_{idx}")
                    arcpy.analysis.Buffer(
                        in_features=study_area_fc,
                        out_feature_class=temp_buffer,
                        buffer_distance_or_field=f"{buffer_distance} Meters",
                        dissolve_option="ALL"
                    )
                    
                    source_url = record['url']
                    arcpy.AddMessage(f"  Connecting to source layer...")
                    
                    temp_source = f"temp_source_{idx}"
                    arcpy.management.MakeFeatureLayer(source_url, temp_source)
                    
                    buffer_action = record['buffer_action'].upper()
                    
                    if buffer_action == "INTERSECT":
                        arcpy.AddMessage("  Selecting features that intersect buffer...")
                        arcpy.management.SelectLayerByLocation(
                            in_layer=temp_source,
                            overlap_type="INTERSECT",
                            select_features=temp_buffer,
                            selection_type="NEW_SELECTION"
                        )
                    elif buffer_action == "CLIP":
                        arcpy.AddMessage("  Will clip features to buffer...")
                        pass
                    else:
                        arcpy.AddWarning(f"  Unknown buffer action: {buffer_action}, using INTERSECT")
                        arcpy.management.SelectLayerByLocation(
                            in_layer=temp_source,
                            overlap_type="INTERSECT",
                            select_features=temp_buffer,
                            selection_type="NEW_SELECTION"
                        )
                    
                    if buffer_action != "CLIP":
                        result = arcpy.management.GetCount(temp_source)
                        count = int(result.getOutput(0))
                        arcpy.AddMessage(f"  Found {count} features")
                        
                        if count == 0:
                            arcpy.AddWarning(f"  No features found for {record['layer_name']}, skipping.. .\n")
                            continue
                    
                    feature_dataset_name = record['feature_dataset']
                    if feature_dataset_name: 
                        feature_dataset = os.path.join(default_gdb, feature_dataset_name)
                        
                        if not arcpy.Exists(feature_dataset):
                            arcpy.AddMessage(f"  Creating feature dataset:  {feature_dataset_name}")
                            arcpy.AddMessage(f"  Using GDA2020 NSW Lambert (EPSG:7858)")
                            sr = arcpy.SpatialReference(7858)
                            arcpy.management.CreateFeatureDataset(
                                default_gdb,
                                feature_dataset_name,
                                sr
                            )
                        
                        output_fc = os.path.join(feature_dataset, record['layer_name'])
                    else:
                        output_fc = os.path.join(default_gdb, record['layer_name'])
                    
                    if arcpy.Exists(output_fc):
                        arcpy.management.Delete(output_fc)
                    
                    if buffer_action == "CLIP":
                        arcpy.AddMessage("  Clipping features to buffer...")
                        arcpy.analysis.Clip(
                            in_features=temp_source,
                            clip_features=temp_buffer,
                            out_feature_class=output_fc
                        )
                    else: 
                        arcpy.AddMessage("  Copying selected features...")
                        arcpy.management.CopyFeatures(temp_source, output_fc)
                    
                    final_result = arcpy.management.GetCount(output_fc)
                    final_count = int(final_result.getOutput(0))
                    
                    if final_count == 0:
                        arcpy.AddWarning(f"  No features in final output, skipping...\n")
                        arcpy.management.Delete(output_fc)
                        continue
                    
                    arcpy.AddMessage("  Adding metadata fields...")
                    
                    existing_fields = [f.name for f in arcpy.ListFields(output_fc)]
                    
                    if "ExtractDate" not in existing_fields: 
                        arcpy.management.AddField(output_fc, "ExtractDate", "DATE")
                    if "ExtractURL" not in existing_fields: 
                        arcpy.management.AddField(output_fc, "ExtractURL", "TEXT", field_length=500)
                    
                    extract_date = datetime.now()
                    extract_url = source_url
                    
                    with arcpy.da.UpdateCursor(output_fc, ["ExtractDate", "ExtractURL"]) as cursor:
                        for row in cursor:
                            row[0] = extract_date
                            row[1] = extract_url
                            cursor.updateRow(row)
                    
                    arcpy.AddMessage(f"  ✓ Successfully processed:  {final_count} features saved")
                    
                    if map_obj:
                        map_obj.addDataFromPath(output_fc)
                        arcpy.AddMessage(f"  ✓ Added to map\n")
                    
                    arcpy.management.Delete(temp_buffer)
                    
                except Exception as layer_error:
                    arcpy.AddWarning(f"  ✗ Error processing {record['layer_name']}: {str(layer_error)}\n")
                    continue
            
            arcpy.AddMessage("="*60)
            arcpy.AddMessage("Creating SiteLotsReport table...")
            arcpy.AddMessage("="*60)
            try:
                lots_layer = os.path.join(default_gdb, "Lots")
                
                if arcpy.Exists(lots_layer):
                    site_lots_report = os.path.join(default_gdb, "SiteLotsReport")
                    
                    if arcpy.Exists(site_lots_report):
                        arcpy.management.Delete(site_lots_report)
                    
                    available_fields = [f.name.lower() for f in arcpy.ListFields(lots_layer)]
                    arcpy.AddMessage(f"  Available fields: {', '.join(available_fields)}")
                    
                    field_mappings = arcpy.FieldMappings()
                    field_mappings.addTable(lots_layer)
                    
                    fields_to_map = {
                        "lotnumber": "Lot",
                        "sectionnumber": "Section",
                        "plannumber": "Plan"
                    }
                    
                    for field in field_mappings.fields:
                        if field.name.lower() not in fields_to_map.keys():
                            field_map_index = field_mappings.findFieldMapIndex(field.name)
                            if field_map_index >= 0:
                                field_mappings.removeFieldMap(field_map_index)
                    
                    for old_name, new_name in fields_to_map.items():
                        try:
                            field_map_index = field_mappings.findFieldMapIndex(old_name)
                            if field_map_index >= 0:
                                field_map = field_mappings.getFieldMap(field_map_index)
                                output_field = field_map.outputField
                                output_field.name = new_name
                                output_field.aliasName = new_name
                                field_map.outputField = output_field
                                field_mappings.replaceFieldMap(field_map_index, field_map)
                                arcpy.AddMessage(f"  Mapped:  {old_name} → {new_name}")
                        except: 
                            arcpy.AddWarning(f"  Could not map field: {old_name}")
                    
                    arcpy.conversion.FeatureClassToFeatureClass(
                        lots_layer,
                        default_gdb,
                        "SiteLotsReport",
                        field_mapping=field_mappings
                    )
                    
                    report_result = arcpy.management.GetCount(site_lots_report)
                    report_count = int(report_result.getOutput(0))
                    
                    arcpy.AddMessage(f"  ✓ SiteLotsReport created:  {report_count} records\n")
                else:
                    arcpy.AddWarning("  ✗ Lots layer not found, skipping SiteLotsReport\n")
            except Exception as e:
                arcpy.AddWarning(f"  ✗ Error creating SiteLotsReport: {str(e)}\n")
            
            arcpy.AddMessage("="*60)
            arcpy.AddMessage("Creating PCT_Report table...")
            arcpy.AddMessage("="*60)
            try:
                pct_layer = os.path.join(default_gdb, "SVTM_PCT")
                
                if arcpy.Exists(pct_layer):
                    pct_result = arcpy.management.GetCount(pct_layer)
                    pct_count = int(pct_result.getOutput(0))
                    
                    if pct_count == 0:
                        arcpy.AddWarning("  SVTM_PCT layer is empty, skipping PCT_Report\n")
                    else:
                        arcpy.AddMessage(f"  Processing {pct_count} PCT polygons...")
                        arcpy.AddMessage("  Calculating polygon areas in m²...")
                        
                        existing_fields = [f.name for f in arcpy.ListFields(pct_layer)]
                        if "area_m" not in existing_fields:
                            arcpy.management.AddField(pct_layer, "area_m", "DOUBLE")
                        
                        arcpy.management.CalculateGeometryAttributes(
                            pct_layer,
                            [["area_m", "AREA_GEODESIC"]],
                            area_unit="SQUARE_METERS"
                        )
                        
                        total_area = 0
                        with arcpy.da.SearchCursor(pct_layer, ["area_m"]) as cursor:
                            for row in cursor:
                                if row[0]: 
                                    total_area += row[0]
                        
                        arcpy.AddMessage(f"  Total PCT area: {total_area:.2f} m²")
                        arcpy.AddMessage("  Calculating percentages of total area...")
                        
                        if "percent_total" not in existing_fields: 
                            arcpy.management.AddField(pct_layer, "percent_total", "DOUBLE")
                        
                        with arcpy.da.UpdateCursor(pct_layer, ["area_m", "percent_total"]) as cursor:
                            for row in cursor:
                                if total_area > 0 and row[0]:
                                    row[1] = (row[0] / total_area) * 100
                                else:
                                    row[1] = 0
                                cursor.updateRow(row)
                        
                        pct_report = os.path.join(default_gdb, "PCT_Report")
                        
                        if arcpy.Exists(pct_report):
                            arcpy.management.Delete(pct_report)
                        
                        arcpy.conversion.TableToTable(
                            pct_layer,
                            default_gdb,
                            "PCT_Report"
                        )
                        
                        arcpy.AddMessage(f"  ✓ PCT_Report created: {pct_count} records\n")
                else:
                    arcpy.AddWarning("  ✗ SVTM_PCT layer not found, skipping PCT_Report\n")
            except Exception as e:
                arcpy.AddWarning(f"  ✗ Error creating PCT_Report:  {str(e)}\n")
            
            arcpy.AddMessage("="*60)
            arcpy.AddMessage("WORKFLOW COMPLETE!")
            arcpy.AddMessage("Standard project layers added successfully")
            arcpy.AddMessage("="*60)
            
        except Exception as e: 
            arcpy.AddError(f"Error adding standard project layers: {str(e)}")
            import traceback
            arcpy.AddError(traceback.format_exc())
        
        return
