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
import time

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
        self.description = "Creates a standardized subject site polygon from an NSW address and writes it to the feature service; optionally continues to extract standard project layers"
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

        # Overwrite existing data checkbox (used in Step 2)
        param5 = arcpy.Parameter(
            displayName="Overwrite existing project data (Step 2)",
            name="overwrite_existing",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param5.value = False

        # Run Step 2 automatically after Step 1
        param6 = arcpy.Parameter(
            displayName="Run Step 2 automatically after Step 1",
            name="run_step2_automatically",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param6.value = True

        # Force re-query even when output exists
        param7 = arcpy.Parameter(
            displayName="Force re-query even if output exists (refresh)",
            name="force_requery",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param7.value = False

        return [param0, param1, param2, param3, param4, param5, param6, param7]

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
        overwrite_flag = bool(parameters[5].value) if len(parameters) > 5 else False
        run_step2_flag = bool(parameters[6].value) if len(parameters) > 6 else True
        force_requery = bool(parameters[7].value) if len(parameters) > 7 else False

        target_layer_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"

        arcpy.AddMessage("=" * 60)
        arcpy.AddMessage("STEP 1 - CREATE SUBJECT SITE (and optionally continue to standard extracts)")
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
                if arcpy.Exists(dissolved):
                    arcpy.management.Delete(dissolved)
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

            # Before appending: check the target feature service for existing active records for this project number and archive them by setting EndDate.
            try:
                arcpy.AddMessage("Checking target feature service for existing active project records (EndDate IS NULL)...")
                temp_target_layer = "temp_target_layer"
                # Make a layer from the feature service (layer URL)
                arcpy.management.MakeFeatureLayer(target_layer_url, temp_target_layer)
                where_clause = f"project_number = '{project_number}' AND EndDate IS NULL"
                arcpy.management.SelectLayerByAttribute(temp_target_layer, "NEW_SELECTION", where_clause)
                existing_count = int(arcpy.management.GetCount(temp_target_layer).getOutput(0))
                if existing_count > 0:
                    arcpy.AddMessage(f"  - Found {existing_count} active record(s). Archiving by setting EndDate to now.")
                    now_dt = datetime.now()
                    # Update EndDate field for each selected feature
                    try:
                        with arcpy.da.UpdateCursor(temp_target_layer, ["EndDate"]) as ucur:
                            for urow in ucur:
                                urow[0] = now_dt
                                ucur.updateRow(urow)
                        arcpy.AddMessage("  ✓ Archived existing record(s) by updating EndDate.")
                    except Exception as ue:
                        arcpy.AddWarning(f"  - Could not update EndDate on remote service: {ue}")
                else:
                    arcpy.AddMessage("  - No active previous record found; nothing to archive.")
                try:
                    arcpy.management.Delete(temp_target_layer)
                except:
                    pass
            except Exception as e:
                arcpy.AddWarning(f"Could not check/archive existing records on feature service: {e}")

            # 4. Append to Feature Service
            arcpy.AddMessage("Writing to feature service...")
            arcpy.management.Append(working_fc, target_layer_url, "NO_TEST")

            # 5. Clean up intermediate fc (we keep working_fc for further processing if it's in default gdb)
            # Note: working_fc is already in default_gdb (temp_property or temp_dissolved)
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
                            dq = f"project_number = '{project_number}' AND EndDate IS Null"
                            target_lyr.definitionQuery = dq
                            arcpy.AddMessage(f"✓ Layer renamed and filtered to project {project_number} AND EndDate IS Null")
                else:
                    arcpy.AddWarning("Map or Layer File not found. Layer not added to map.")
            except Exception as e:
                arcpy.AddWarning(f"Could not update map: {str(e)}")

            arcpy.AddMessage("\nSTEP 1 COMPLETE.")

            # Continue to Step 2 using the study area we just created if user requested it
            if run_step2_flag:
                arcpy.AddMessage("Proceeding to STEP 2 using the created study area...")
                try:
                    self._run_step2_with_study_area(aprx, working_fc, project_number, overwrite_flag, force_requery)
                except Exception as e:
                    arcpy.AddError(f"Error while running Step 2 after Step 1: {e}")
            else:
                arcpy.AddMessage("Step 2 was not requested to run automatically. Process completed after Step 1.")

            arcpy.AddMessage("\nSUCCESS!")

        except Exception as e:
            arcpy.AddError(f"\n✗ Error: {str(e)}")
            import traceback
            arcpy.AddError(traceback.format_exc())
        return

    def _run_step2_with_study_area(self, aprx, study_area_fc, project_number, overwrite_flag=False, force_requery=False):
        """
        Runs the "Add Standard Project Layers" process using the provided study_area_fc
        produced in Step 1.

        overwrite_flag: boolean - if True, layers in the default GDB will be overwritten;
                        otherwise they will be skipped.
        force_requery: boolean - if True, re-query the service and refresh the output even if it exists
                        (will still respect overwrite_flag regarding whether to replace).
        """
        reference_table_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15"
        arcpy.AddMessage("=" * 60)
        arcpy.AddMessage("STEP 2 - ADD PROJECT LAYERS (continuing from Step 1)")
        arcpy.AddMessage("=" * 60)

        # Summary trackers
        skipped = []
        extracted_new = []
        replaced = []
        failed = []

        try:
            default_gdb = aprx.defaultGeodatabase
            map_obj = aprx.activeMap
            token = self._get_token()

            # compute total site area in square meters for later use (geodesic)
            site_area_m2 = 0.0
            with arcpy.da.SearchCursor(study_area_fc, ["SHAPE@"]) as sc:
                for r in sc:
                    site_area_m2 = r[0].getArea("GEODESIC", "SQUAREMETERS")
                    break

            arcpy.AddMessage(f"  ✓ Study area size: {site_area_m2:.2f} m²")

            # Query the Standard Connection Reference Table for ProjectType = "all"
            arcpy.AddMessage("Querying Standard Connection Reference Table for ProjectType = 'all' ...")
            params = {"where": "ProjectType='all'", "outFields": "*", "f": "json"}
            if token:
                params["token"] = token
            query_url = f"{reference_table_url}/query?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(query_url, timeout=60) as resp:
                ref_data = json.loads(resp.read().decode())

            features = ref_data.get("features", [])
            if not features:
                arcpy.AddWarning("No standard connections found for ProjectType = 'all'.")
            else:
                arcpy.AddMessage(f"  ✓ Found {len(features)} reference records.")

            processed_outputs = []  # track extracted layers for reports

            def _get_attr_ci(attrs, key):
                # case-insensitive attribute accessor
                for k, v in attrs.items():
                    if k.lower() == key.lower():
                        return v
                return None

            for idx, feat in enumerate(features, start=1):
                attrs = feat.get("attributes", {})
                service_url = _get_attr_ci(attrs, "URL") or _get_attr_ci(attrs, "Url") or _get_attr_ci(attrs, "url")
                site_buffer = _get_attr_ci(attrs, "SiteBuffer") or _get_attr_ci(attrs, "sitebuffer") or 0
                buffer_action = _get_attr_ci(attrs, "BufferAction") or _get_attr_ci(attrs, "bufferaction") or "INTERSECT"
                feature_dataset_name = _get_attr_ci(attrs, "FeatureDatasetName") or _get_attr_ci(attrs, "FeatureDataset") or "ProjectData"
                short_name = _get_attr_ci(attrs, "ShortName") or _get_attr_ci(attrs, "Shortname") or f"Layer_{idx}"

                arcpy.AddMessage(f"Processing reference record {idx}: ShortName='{short_name}' URL='{service_url}' Buffer={site_buffer} Action={buffer_action}")

                # Validate service URL
                if not service_url:
                    arcpy.AddWarning(f"  - No URL for reference record {short_name}; skipping.")
                    skipped.append(short_name)
                    continue

                # Build intended output path early (for quick existence check)
                fd_path = os.path.join(default_gdb, feature_dataset_name)
                out_fc = os.path.join(fd_path, short_name)

                # QUICK EXISTENCE CHECK (to avoid unnecessary service calls)
                if arcpy.Exists(out_fc):
                    if not overwrite_flag and not force_requery:
                        arcpy.AddMessage(f"  - Output {out_fc} already exists. Overwrite disabled and force re-query not set -> SKIP")
                        skipped.append(short_name)
                        continue
                    else:
                        arcpy.AddMessage(f"  - Output {out_fc} exists. Will refresh via temporary extract and replace after success.")

                # 2.1 Buffer the subject site by the distance in SiteBuffer (meters)
                try:
                    distance_m = float(site_buffer) if site_buffer not in (None, '') else 0.0
                except:
                    distance_m = 0.0

                if distance_m > 0:
                    buffer_fc = os.path.join("memory", f"buf_{short_name}")
                    if arcpy.Exists(buffer_fc):
                        arcpy.management.Delete(buffer_fc)
                    arcpy.analysis.Buffer(study_area_fc, buffer_fc, f"{distance_m} Meters", method="GEODESIC")
                else:
                    buffer_fc = study_area_fc

                # 2.2 Connect to the target feature layer and subset by buffer polygon
                temp_layer_name = f"temp_layer_{idx}_{int(time.time())}"
                made_layer = False
                try:
                    # Try the normal approach first
                    arcpy.management.MakeFeatureLayer(service_url, temp_layer_name)
                    made_layer = True
                except Exception as e:
                    arcpy.AddWarning(f"  - Could not make feature layer from URL '{service_url}': {e}")
                    # we'll try the REST fallback below

                # Attempt a spatial selection. If it fails, fall back to a REST query for OBJECTIDs and recreate the layer with a WHERE clause.
                selection_succeeded = False
                try:
                    if made_layer:
                        arcpy.management.SelectLayerByLocation(temp_layer_name, "INTERSECT", buffer_fc)
                        selection_succeeded = True
                    else:
                        raise Exception("Layer creation failed; attempting REST fallback")
                except Exception as sel_err:
                    arcpy.AddWarning(f"  - Selection by location failed for '{short_name}': {sel_err}")
                    # Clean up any partially created layer
                    try:
                        if made_layer:
                            arcpy.management.Delete(temp_layer_name)
                    except:
                        pass

                    # REST fallback: query the service /query endpoint for OBJECTIDs intersecting the buffer geometry
                    try:
                        # get a single geometry JSON from buffer_fc (esri JSON)
                        geom_json = None
                        with arcpy.da.SearchCursor(buffer_fc, ["SHAPE@"]) as gcur:
                            for grow in gcur:
                                geom_json = grow[0].JSON
                                break

                        if not geom_json:
                            arcpy.AddWarning(f"  - Could not obtain geometry JSON for fallback on '{short_name}'.")
                            raise Exception("No geometry available for fallback query")

                        query_layer_url = service_url.rstrip('/') + "/query"
                        qparams = {
                            "geometry": geom_json,
                            "geometryType": "esriGeometryPolygon",
                            "spatialRel": "esriSpatialRelIntersects",
                            "inSR": "4326",
                            "returnIdsOnly": "true",
                            "f": "json"
                        }
                        if token:
                            qparams["token"] = token

                        qurl = f"{query_layer_url}?{urllib.parse.urlencode(qparams)}"
                        with urllib.request.urlopen(qurl, timeout=60) as qresp:
                            qdata = json.loads(qresp.read().decode())

                        object_ids = qdata.get("objectIds") or []
                        if not object_ids:
                            arcpy.AddMessage(f"  - REST query returned no features for '{short_name}'; skipping.")
                            failed.append(short_name)
                            # ensure no leftover
                            try:
                                if arcpy.Exists(temp_layer_name):
                                    arcpy.management.Delete(temp_layer_name)
                            except:
                                pass
                            continue

                        # Determine object id field name if provided
                        oid_field = qdata.get("objectIdFieldName") or "OBJECTID"
                        # Create a WHERE clause safely (OBJECTID list) and make a layer from the service using that filter
                        id_list = ",".join(str(int(i)) for i in object_ids)
                        where_ids = f"{oid_field} IN ({id_list})"
                        try:
                            arcpy.management.MakeFeatureLayer(service_url, temp_layer_name, where_clause=where_ids)
                        except Exception as e2:
                            arcpy.AddWarning(f"  - Could not create filtered layer from service for '{short_name}': {e2}")
                            failed.append(short_name)
                            # ensure no leftover
                            try:
                                if arcpy.Exists(temp_layer_name):
                                    arcpy.management.Delete(temp_layer_name)
                            except:
                                pass
                            continue

                        # selection with the filtered layer is effectively successful
                        selection_succeeded = True

                    except Exception as fb_err:
                        arcpy.AddWarning(f"  - REST fallback failed for '{short_name}': {fb_err}")
                        # nothing more we can do for this reference record
                        failed.append(short_name)
                        # ensure no leftover
                        try:
                            if arcpy.Exists(temp_layer_name):
                                arcpy.management.Delete(temp_layer_name)
                        except:
                            pass
                        continue

                # At this point selection_succeeded indicates we have a usable temp_layer_name (either original selection or filtered layer)
                if not selection_succeeded:
                    arcpy.AddWarning(f"  - Could not select features for '{short_name}'; skipping.")
                    try:
                        if arcpy.Exists(temp_layer_name):
                            arcpy.management.Delete(temp_layer_name)
                    except:
                        pass
                    if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                        arcpy.management.Delete(buffer_fc)
                    failed.append(short_name)
                    continue

                count = int(arcpy.management.GetCount(temp_layer_name).getOutput(0))
                arcpy.AddMessage(f"  - Selected {count} features from service.")

                if count < 1:
                    arcpy.AddMessage(f"  - No features selected for '{short_name}', skipping.")
                    try:
                        arcpy.management.Delete(temp_layer_name)
                    except:
                        pass
                    if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                        arcpy.management.Delete(buffer_fc)
                    skipped.append(short_name)
                    continue

                # Ensure feature dataset exists in default GDB (create now, since we're going to write)
                if not arcpy.Exists(fd_path):
                    arcpy.AddMessage(f"  - Creating feature dataset '{feature_dataset_name}' in default geodatabase.")
                    arcpy.management.CreateFeatureDataset(default_gdb, feature_dataset_name, arcpy.SpatialReference(8058))

                # Write to a temporary output first (in default_gdb) then replace existing only on success
                timestamp = int(time.time())
                tmp_out = os.path.join(default_gdb, f"tmp_extract_{short_name}_{timestamp}")
                try:
                    if buffer_action and buffer_action.strip().upper() == "CLIP":
                        # Clip to buffer -> write to tmp_out
                        arcpy.analysis.Clip(temp_layer_name, buffer_fc, tmp_out)
                    else:
                        # INTERSECT behavior: copy the selected features as-is to tmp_out
                        arcpy.management.CopyFeatures(temp_layer_name, tmp_out)
                except Exception as e:
                    arcpy.AddWarning(f"  - Error extracting features for '{short_name}': {e}")
                    try:
                        arcpy.management.Delete(temp_layer_name)
                    except:
                        pass
                    if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                        arcpy.management.Delete(buffer_fc)
                    failed.append(short_name)
                    # Clean up tmp_out if partially created
                    try:
                        if arcpy.Exists(tmp_out):
                            arcpy.management.Delete(tmp_out)
                    except:
                        pass
                    continue

                # 2.4 Add additional attributes: ExtractDate & ExtractURL on tmp_out
                try:
                    if not arcpy.ListFields(tmp_out, "ExtractDate"):
                        arcpy.management.AddField(tmp_out, "ExtractDate", "DATE")
                    if not arcpy.ListFields(tmp_out, "ExtractURL"):
                        arcpy.management.AddField(tmp_out, "ExtractURL", "TEXT", field_length=2048)
                    now_dt = datetime.now()
                    with arcpy.da.UpdateCursor(tmp_out, ["ExtractDate", "ExtractURL"]) as uc:
                        for row in uc:
                            row[0] = now_dt
                            row[1] = service_url
                            uc.updateRow(row)
                except Exception as e:
                    arcpy.AddWarning(f"  - Could not add/populate ExtractDate/ExtractURL for '{short_name}': {e}")
                    # proceed - this is non-fatal

                # Now replace the existing out_fc only after tmp_out was successfully created
                try:
                    # If existing present and we are replacing, delete it first (now that tmp_out exists)
                    if arcpy.Exists(out_fc):
                        try:
                            arcpy.management.Delete(out_fc)
                            arcpy.AddMessage(f"  - Deleted existing {out_fc}")
                        except Exception as e:
                            arcpy.AddWarning(f"  - Could not delete existing output {out_fc}: {e}. Will attempt to clean up tmp and skip replacing.")
                            # cleanup tmp_out and move on
                            try:
                                arcpy.management.Delete(tmp_out)
                            except:
                                pass
                            failed.append(short_name)
                            try:
                                arcpy.management.Delete(temp_layer_name)
                            except:
                                pass
                            if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                                arcpy.management.Delete(buffer_fc)
                            continue

                        replaced.append(short_name)
                    else:
                        extracted_new.append(short_name)

                    # Move tmp_out to final location by copying features (ensures correct path/name inside FD)
                    arcpy.management.CopyFeatures(tmp_out, out_fc)
                    # Remove tmp_out
                    try:
                        arcpy.management.Delete(tmp_out)
                    except:
                        pass

                    arcpy.AddMessage(f"  ✓ Extracted '{short_name}' to {out_fc}")
                    processed_outputs.append({"shortname": short_name, "path": out_fc})

                except Exception as e:
                    arcpy.AddWarning(f"  - Could not move temporary extract to final location for '{short_name}': {e}")
                    failed.append(short_name)
                    # attempt cleanup
                    try:
                        if arcpy.Exists(tmp_out):
                            arcpy.management.Delete(tmp_out)
                    except:
                        pass
                    try:
                        arcpy.management.Delete(temp_layer_name)
                    except:
                        pass
                    if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                        arcpy.management.Delete(buffer_fc)
                    continue

                # cleanup
                try:
                    arcpy.management.Delete(temp_layer_name)
                except:
                    pass
                if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                    try:
                        arcpy.management.Delete(buffer_fc)
                    except:
                        pass

            # 4. Create the SiteLotsReport table in default GDB
            arcpy.AddMessage("Creating SiteLotsReport table...")
            lots_fc = None
            for po in processed_outputs:
                if "lot" in po["shortname"].lower():
                    lots_fc = po["path"]
                    break

            if not lots_fc:
                arcpy.AddWarning("Could not find a 'Lots' layer among processed outputs to build SiteLotsReport. Skipping SiteLotsReport.")
            else:
                arcpy.AddMessage(f"  - Using Lots layer at {lots_fc}")
                lots_layer = "temp_lots_layer"
                try:
                    arcpy.management.MakeFeatureLayer(lots_fc, lots_layer)
                    arcpy.management.SelectLayerByLocation(lots_layer, "WITHIN", study_area_fc)
                    selected_count = int(arcpy.management.GetCount(lots_layer).getOutput(0))
                    arcpy.AddMessage(f"  - {selected_count} lots within subject site.")
                    report_table = os.path.join(default_gdb, "SiteLotsReport")
                    if arcpy.Exists(report_table):
                        arcpy.management.Delete(report_table)
                    arcpy.management.CreateTable(default_gdb, "SiteLotsReport")
                    arcpy.management.AddField(report_table, "Lot", "TEXT", field_length=50)
                    arcpy.management.AddField(report_table, "Section", "TEXT", field_length=50)
                    arcpy.management.AddField(report_table, "Plan", "TEXT", field_length=50)
                    arcpy.management.AddField(report_table, "PlanLotArea", "DOUBLE")
                    arcpy.management.AddField(report_table, "PlanLotAreaUnits", "TEXT", field_length=50)

                    src_fields = [f.name for f in arcpy.ListFields(lots_fc)]
                    def find_field(names):
                        for name in names:
                            for f in src_fields:
                                if f.lower() == name.lower():
                                    return f
                        return None

                    lot_f = find_field(["lotnumber", "lot_no", "lot"])
                    section_f = find_field(["sectionnumber", "section_no", "section"])
                    plan_f = find_field(["plannumber", "plan_number", "plan"])
                    plan_area_f = find_field(["planlotarea", "plan_lot_area", "planlotarea"])
                    plan_area_units_f = find_field(["planlotareaunits", "plan_lot_area_units", "planlotareaunits"])

                    insert_fields = ["Lot", "Section", "Plan", "PlanLotArea", "PlanLotAreaUnits"]
                    # Build a SearchCursor field list containing only existing fields
                    src_field_list = [lot_f, section_f, plan_f, plan_area_f, plan_area_units_f]
                    actual_src_fields = [f for f in src_field_list if f]
                    if not actual_src_fields:
                        arcpy.AddWarning("No suitable source fields found in Lots layer to build SiteLotsReport; skipping SiteLotsReport.")
                    else:
                        # Use searchcursor on selected lots (via lots_layer) so we only insert selected features
                        with arcpy.da.InsertCursor(report_table, insert_fields) as ins, arcpy.da.SearchCursor(lots_layer, actual_src_fields) as src:
                            for srow in src:
                                # Map values back to the fixed insert order, filling defaults where source fields missing
                                out_row = []
                                for fld in [lot_f, section_f, plan_f, plan_area_f, plan_area_units_f]:
                                    if fld:
                                        # find index of fld in actual_src_fields
                                        try:
                                            idx = actual_src_fields.index(fld)
                                            val = srow[idx]
                                        except ValueError:
                                            val = None
                                    else:
                                        val = None

                                    # apply sensible defaults: text -> '', numeric -> None
                                    if val is None:
                                        if fld == plan_area_f:
                                            out_row.append(None)
                                        else:
                                            out_row.append('')
                                    else:
                                        out_row.append(val)
                                ins.insertRow(out_row)

                    arcpy.AddMessage(f"  ✓ SiteLotsReport created: {report_table}")
                except Exception as e:
                    arcpy.AddWarning(f"  - Error creating SiteLotsReport: {e}")
                finally:
                    try:
                        arcpy.management.Delete(lots_layer)
                    except:
                        pass

            # 5. Create the PCT_Report table
            arcpy.AddMessage("Creating PCT_REPORT table...")
            pct_fc = None
            for po in processed_outputs:
                if "pct" in po["shortname"].lower() or "svtm_pct" in po["shortname"].lower():
                    pct_fc = po["path"]
                    break

            if not pct_fc:
                arcpy.AddWarning("Could not find an SVTM_PCT layer among processed outputs. Skipping PCT_REPORT.")
            else:
                arcpy.AddMessage(f"  - Using PCT layer at {pct_fc}")

                if not arcpy.ListFields(pct_fc, "area_m"):
                    arcpy.management.AddField(pct_fc, "area_m", "DOUBLE")
                if not arcpy.ListFields(pct_fc, "SiteCoveragePct"):
                    arcpy.management.AddField(pct_fc, "SiteCoveragePct", "DOUBLE")

                with arcpy.da.UpdateCursor(pct_fc, ["SHAPE@", "area_m", "SiteCoveragePct"]) as uc:
                    for row in uc:
                        geom = row[0]
                        a_m = geom.getArea("GEODESIC", "SQUAREMETERS")
                        row[1] = a_m
                        pct = (100.0 * a_m / site_area_m2) if site_area_m2 > 0 else 0.0
                        row[2] = round(pct, 1)
                        uc.updateRow(row)

                pct_fields = [f.name for f in arcpy.ListFields(pct_fc)]
                def get_field_by_candidates(cands):
                    for c in cands:
                        for f in pct_fields:
                            if f.lower() == c.lower():
                                return f
                    return None

                pctid_field = get_field_by_candidates(["PCTID", "pctid", "PCT_ID"])
                pctname_field = get_field_by_candidates(["PCTName", "pctname", "PCT_Name", "PCTNAME"])

                if not pctid_field or not pctname_field:
                    arcpy.AddWarning("Could not find PCTID and PCTName fields in PCT layer; cannot create PCT_Report.")
                else:
                    summary = {}
                    with arcpy.da.SearchCursor(pct_fc, [pctid_field, pctname_field, "area_m", "SiteCoveragePct"]) as sc:
                        for r in sc:
                            key = (r[0], r[1])
                            if key not in summary:
                                summary[key] = {"area_m": 0.0, "sitecov": 0.0}
                            summary[key]["area_m"] += (r[2] or 0.0)
                            summary[key]["sitecov"] += (r[3] or 0.0)

                    pct_table = os.path.join(default_gdb, "PCT_Report")
                    if arcpy.Exists(pct_table):
                        arcpy.management.Delete(pct_table)
                    arcpy.management.CreateTable(default_gdb, "PCT_Report")
                    arcpy.management.AddField(pct_table, "PCTID", "TEXT", field_length=50)
                    arcpy.management.AddField(pct_table, "PCTName", "TEXT", field_length=255)
                    arcpy.management.AddField(pct_table, "Sum_area_m", "DOUBLE")
                    arcpy.management.AddField(pct_table, "Sum_SiteCoveragePct", "DOUBLE")

                    with arcpy.da.InsertCursor(pct_table, ["PCTID", "PCTName", "Sum_area_m", "Sum_SiteCoveragePct"]) as ins:
                        for (pid, pname), vals in summary.items():
                            ins.insertRow([str(pid), str(pname), vals["area_m"], round(vals["sitecov"], 1)])

                    arcpy.AddMessage(f"  ✓ PCT_Report created: {pct_table}")

            # Final summary of processing for QA
            arcpy.AddMessage("\nExtraction summary:")
            arcpy.AddMessage(f"  - Extracted new layers: {len(extracted_new)}")
            if extracted_new:
                arcpy.AddMessage(f"    {extracted_new}")
            arcpy.AddMessage(f"  - Replaced (overwritten) layers: {len(replaced)}")
            if replaced:
                arcpy.AddMessage(f"    {replaced}")
            arcpy.AddMessage(f"  - Skipped layers (existing and not requested to refresh): {len(skipped)}")
            if skipped:
                arcpy.AddMessage(f"    {skipped}")
            arcpy.AddMessage(f"  - Failed layers: {len(failed)}")
            if failed:
                arcpy.AddMessage(f"    {failed}")

            arcpy.AddMessage("\nSTEP 2 COMPLETE - Standard project layers extracted and reports created.")

        except Exception as e:
            arcpy.AddError(f"Error executing Step 2: {str(e)}")
            import traceback
            arcpy.AddError(traceback.format_exc())
        return


class AddStandardProjectLayers(object):
    def __init__(self):
        self.label = "Step 2 - Add Standard Project Layers"
        self.description = "Adds standard project layers based on the subject site (standalone use)"
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

        # Overwrite checkbox for standalone Step 2
        param1 = arcpy.Parameter(
            displayName="Overwrite existing project data",
            name="overwrite_existing",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param1.value = False

        # Force re-query even if output exists
        param2 = arcpy.Parameter(
            displayName="Force re-query even if output exists (refresh)",
            name="force_requery",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param2.value = False

        return [param0, param1, param2]

    def isLicensed(self):
        return True

    def _get_token(self):
        try:
            info = arcpy.GetSigninToken()
            return info.get("token") if info else None
        except:
            return None

    def _get_unique_project_numbers(self, target_layer_url, token):
        # Return distinct project_number values only from active records (EndDate IS NULL)
        params = {"where": "EndDate IS NULL", "outFields": "project_number", "returnDistinctValues": "true", "f": "json"}
        if token:
            params["token"] = token
        query_url = f"{target_layer_url}/query?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(query_url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        # Build unique sorted list (ensure strings, exclude nulls)
        values = sorted({str(feat['attributes'].get('project_number')) for feat in data.get('features', []) if feat['attributes'].get('project_number') is not None})
        return values

    def _get_study_area_by_project_number(self, target_layer_url, token, project_number):
        # Safely escape single quotes inside the project_number value only
        safe_project_number = project_number.replace("'", "''") if project_number else project_number
        # Ensure we select only the active record(s) (EndDate IS NULL) for the project number
        where = f"project_number='{safe_project_number}' AND EndDate IS NULL"

        params = {"where": where, "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json"}
        if token:
            params["token"] = token
        query_url = f"{target_layer_url}/query?{urllib.parse.urlencode(params)}"

        with urllib.request.urlopen(query_url, timeout=30) as resp:
            data = json.loads(resp.read().decode())

        if not data.get('features'):
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
            # Always attempt to refresh the project number list from the service so the dropdown is up to date
            list_values = self._get_unique_project_numbers(url, token)
            parameters[0].filter.list = list_values

            # if the current parameter value matches a returned project number, make sure it's selected
            if parameters[0].valueAsText and parameters[0].valueAsText in list_values:
                parameters[0].value = parameters[0].valueAsText
        except Exception as e:
            # don't block the UI; show a warning to help troubleshooting
            try:
                arcpy.AddWarning(f"Could not refresh project number list from service: {e}")
            except:
                pass
        return

    def execute(self, parameters, messages):
        project_number = parameters[0].valueAsText
        overwrite_flag = bool(parameters[1].value) if len(parameters) > 1 else False
        force_requery = bool(parameters[2].value) if len(parameters) > 2 else False
        target_layer_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"

        arcpy.AddMessage("=" * 60)
        arcpy.AddMessage("STEP 2 - ADD PROJECT LAYERS (standalone)")
        arcpy.AddMessage("=" * 60)

        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            map_obj = aprx.activeMap

            if not map_obj:
                arcpy.AddError("No active map found. Please open a map view.")
                return

            token = self._get_token()

            # Re-query the service to ensure we have the latest list before proceeding
            try:
                latest_list = self._get_unique_project_numbers(target_layer_url, token)
                if project_number not in latest_list:
                    arcpy.AddWarning(f"Project number '{project_number}' was not found in the current service list. Re-querying will still be attempted.")
                else:
                    arcpy.AddMessage(f"Project number '{project_number}' confirmed in service ({len(latest_list)} total projects).")
            except Exception as e:
                arcpy.AddWarning(f"Could not refresh project number list before execution: {e}")

            # 1. Retrieve the study area (only active records: EndDate IS NULL)
            arcpy.AddMessage(f"Retrieving study area for Project {project_number} (EndDate IS NULL)...")
            study_area_fc = self._get_study_area_by_project_number(target_layer_url, token, project_number)

            if not study_area_fc:
                arcpy.AddError(f"Could not find an active (EndDate IS NULL) study area for Project {project_number}. Ensure the project exists and has EndDate = NULL in the service.")
                return

            # Hand over to the CreateSubjectSite implementation to run the step2 flow,
            # passing the overwrite and force_requery flags from the tool UI.
            CreateSubjectSite()._run_step2_with_study_area(aprx, study_area_fc, project_number, overwrite_flag, force_requery)

            arcpy.AddMessage("\nSUCCESS - Project Layers Added.")

        except Exception as e:
            arcpy.AddError(f"Error executing Step 2: {str(e)}")
            import traceback
            arcpy.AddError(traceback.format_exc())
        return
