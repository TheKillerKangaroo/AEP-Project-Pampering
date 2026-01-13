# -*- coding: utf-8 -*-
#  $$\   $$\ $$\ $$\ $$\                           $$\   $$\                                                                      
#  $$ | $$  |\__|$$ |$$ |                          $$ | $$  |                                                                     
#  $$ |$$  / $$\ $$ |$$ | $$$$$$\   $$$$$$\        $$ |$$  / $$$$$$\  $$$$$$$\   $$$$$$\   $$$$$$\   $$$$$$\   $$$$$$\   $$$$$$\  
#  $$$$$  /  $$ |$$ |$$ |$$  __$$\ $$  __$$\       $$$$$  /  \____$$\ $$  __$$\ $$  __$$\  \____$$\ $$  __$$\ $$  __$$\ $$  __$$\ 
#  $$  $$<   $$ |$$ |$$ |$$$$$$$$ |$$ |  \__|      $$  $$<   $$$$$$$ |$$ |  $$ |$$ /  $$ | $$$$$$$ |$$ |  \__|$$ /  $$ |$$ /  $$ |
#  $$ |\$$\  $$ |$$ |$$ |$$   ____|$$ |            $$ |\$$\ $$  __$$ |$$ |  $$ |$$ |  $$ |$$  __$$ |$$ |      $$ |  $$ |$$ |  $$ |
#  $$ | \$$\ $$ |$$ |$$ |\$$$$$$$\ $$ |            $$ | \$$\\$$$$$$$ |$$ |  $$ |\$$$$$$$ |\$$$$$$$ |$$ |      \$$$$$$  |\$$$$$$  |
#  \__|  \__|\__|\__|\__| \_______|\__|            \__|  \__|\_______|\__|  \__| \____$$ | \_______|\__|       \______/  \______/ 
                                                                             $$\   $$ |                                        
                                                                             \$$$$$$  |                                        
                                                                              \______/                                         
"""
                                                                                                    
                                                                                                    
                                                                                                    
                .......   ........                                                                  
            .:---------------------:.                  .%%%%%%.    :%%%%%%%%%%%  #%%%%%%%#+         
          .---------------------------:.               :%%%%%%:    :%%%%%%%%%%%  #%%%%%%%%%%:       
         ------------------------=------.              *%%%%%%*    :%%%#         #%%%. .:%%%%.      
       .-----------------------#@@=------:.           .%%%+%%%%.   :%%%#         #%%%.  .%%%%.      
      .----------------------@@@%---------.           :%%%.#%%%:   :%%%#         #%%%.  .%%%%.      
      .-------+@@@@*------=@@%=------------.          =%%%.:%%%=   :%%%#         #%%%.  .%%%%.      
      :---------#@@@@*++@@#.---------------.         .%%%# .%%%%   :%%%%%%%%%:   #%%%-::+%%%%.      
      :---------=#@@@@@@@..----------------.         .%%%-  #%%%:  :%%%%%%%%%:   #%%%%%%%%%%.       
      .-----------.:+#@@@@@#=--------------.         -%%%   +%%%-  :%%%#         #%%%#**+=.         
      .-----------------------------------.          *%%%****%%%*  :%%%#         #%%%.              
       .-------------++------------------:.         .%%%%%%%%%%%%. :%%%#         #%%%.              
         :-----------=------------------.           :%%%-....#%%%- :%%%#.......  #%%%.              
          .---------------------------:             +%%%     -%%%+ :%%%%%%%%%%%  #%%%.              
            ..:--------------------:.              .%%%%     .%%%% :%%%%%%%%%%%  #%%%.              
                                                                                                                                                            
                                                                                                    
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
import re
import uuid

# Global Path to Layer File (Standard Styling)
LAYERFILE_PATH = r"G:\Shared drives\99.3 GIS Admin\Production\Layer Files\AEP - Study Area.lyrx"


# Module-level helper: build a SQL WHERE clause that respects the target field type when possible.
def build_project_defq(project_number, layer=None):
    """
    Build a WHERE clause for project_number + EndDate IS NULL that matches the
    target field type when a layer object/path is available.

    - If `layer` is provided, inspect the project_number field type via arcpy.ListFields(layer)
      and emit a numeric comparison for numeric field types, otherwise a quoted string.
    - If `layer` is not provided, fall back to value-based detection (digits -> numeric),
      but callers should pass a layer when possible to avoid invalid SQL.
    Returns full clause, e.g. "project_number = 6666 AND EndDate IS NULL" or
    "project_number = 'ABC123' AND EndDate IS NULL".
    """
    if project_number is None:
        return "EndDate IS NULL"

    pn = str(project_number).strip()

    def quoted(val):
        return "'" + val.replace("'", "''") + "'"

    # If layer provided, inspect fields on it to determine type
    if layer is not None:
        try:
            for f in arcpy.ListFields(layer):
                if f.name.lower() in ("project_number", "projectnumber", "project_num", "projectnum"):
                    ftype = getattr(f, "type", "").lower()
                    # numeric types used by arcpy: 'smallinteger', 'integer', 'single', 'double', 'oid', 'long'
                    if ftype in ("smallinteger", "integer", "single", "double", "oid", "long"):
                        try:
                            if pn.isdigit():
                                return f"project_number = {int(pn)} AND EndDate IS Null"
                            fv = float(pn)
                            if fv.is_integer():
                                return f"project_number = {int(fv)} AND EndDate IS Null"
                        except Exception:
                            # If casting fails, fall back to quoted
                            return f"project_number = {quoted(pn)} AND EndDate IS Null"
                    else:
                        # text-like field -> quote
                        return f"project_number = {quoted(pn)} AND EndDate IS Null"
        except Exception:
            # if field inspection fails, fall back to value-based below
            pass

    # No layer or inspection failed -> fall back to value-based detection
    if pn.isdigit():
        return f"project_number = {int(pn)} AND EndDate IS Null"
    try:
        f = float(pn)
        if f.is_integer():
            return f"project_number = {int(f)} AND EndDate IS Null"
    except Exception:
        pass

    return f"project_number = {quoted(pn)} AND EndDate IS Null"


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

    # Helper to normalise addDataFromPath return and extract a usable layer object
    def _normalize_added(self, added):
        """
        addDataFromPath may return a single Layer object, a GroupLayer, or a list.
        Return a tuple (top_object, child_layer_or_none, parent_object_or_none)
        - top_object: the object returned or first item when list
        - child_layer_or_none: the actual sublayer if top_object is a group and has children; else same as top_object
        - parent_object_or_none: the original top_object (useful to remove parent group after extracting child)
        """
        top = added
        try:
            # some runtimes return lists
            if isinstance(added, (list, tuple)):
                if len(added) > 0:
                    top = added[0]
                else:
                    top = None
        except Exception:
            top = added

        if top is None:
            return (None, None, None)

        parent = top
        child = top
        try:
            if getattr(top, "isGroupLayer", False):
                # prefer first child that supports a name/connectionProperties
                try:
                    children = top.listLayers()
                    if children:
                        # pick first child that looks like a layer
                        for c in children:
                            if getattr(c, "connectionProperties", None) is not None or getattr(c, "isGroupLayer", False) is False:
                                child = c
                                break
                        # if none matched, just take first
                        if child is None and len(children) > 0:
                            child = children[0]
                except Exception:
                    child = None
        except Exception:
            pass

        return (top, child or top, parent if parent is not child else None)

    def _apply_style_swap(self, site_map, data_layer, style_path, display_name=None, set_defq=None):
        """
        Attempt Headmaster-style swap:
        - import style (addDataFromPath)
        - extract actual style sublayer
        - updateConnectionProperties to point at data_layer connection
        - if updateConnectionProperties fails, try ApplySymbologyFromLayer on the style layer
        - set definition query on style layer if provided and supported
        - remove original data_layer and any parent imported group
        Returns final_layer (the styled layer) or None on complete failure.
        """
        final_layer = data_layer
        try:
            added = site_map.addDataFromPath(style_path)
        except Exception as e:
            arcpy.AddWarning(f"  - Could not import style '{style_path}': {e}")
            return None

        top, style_layer, parent = self._normalize_added(added)
        if style_layer is None:
            arcpy.AddWarning(f"  - Imported style produced no usable layer object: {style_path}")
            try:
                if top and top is not data_layer:
                    site_map.removeLayer(top)
            except Exception:
                pass
            return None

        # capture connection and def query from data_layer
        try:
            conn_props = data_layer.connectionProperties
        except Exception:
            conn_props = None
        try:
            def_query = data_layer.definitionQuery if data_layer.supports("DEFINITIONQUERY") else None
        except Exception:
            def_query = None

        update_ok = False
        # try to update connection properties on style_layer
        if conn_props:
            try:
                style_layer.updateConnectionProperties(style_layer.connectionProperties, conn_props)
                update_ok = True
            except Exception as e:
                arcpy.AddWarning(f"  - updateConnectionProperties failed for '{style_path}': {e}")
                # attempt ApplySymbologyFromLayer fallback on the imported style layer
                try:
                    arcpy.management.ApplySymbologyFromLayer(style_layer, style_path)
                    update_ok = True
                    arcpy.AddMessage(f"  • Applied symbology to imported style layer via ApplySymbologyFromLayer as workaround.")
                except Exception as e2:
                    arcpy.AddWarning(f"  - ApplySymbologyFromLayer on imported style also failed: {e2}")

        # restore def query from data_layer (or provided)
        try:
            if set_defq and style_layer.supports("DEFINITIONQUERY"):
                style_layer.definitionQuery = set_defq
            elif def_query and style_layer.supports("DEFINITIONQUERY"):
                style_layer.definitionQuery = def_query
        except Exception:
            pass

        # rename style layer to display_name if provided
        try:
            if display_name:
                style_layer.name = display_name
        except Exception:
            pass

        # remove original data layer (only after we've attempted to apply symbology)
        try:
            site_map.removeLayer(data_layer)
        except Exception:
            # if removal fails, try hiding it
            try:
                data_layer.visible = False
            except:
                pass

        # remove parent import wrapper if it's a group and different from style_layer
        try:
            if parent and parent is not style_layer:
                try:
                    site_map.removeLayer(parent)
                except Exception:
                    pass
        except Exception:
            pass

        final_layer = style_layer
        return final_layer

    def _cleanup_duplicates(self, site_map, final_layer, display_name, preexisting_names=None):
        """
        Remove layers with the same display name that were present before this run.
        - preexisting_names: optional set of layer names that existed before we added the new layer(s).
          Only layers whose name is in preexisting_names will be removed. This avoids removing
          layers that we added during this run.
        - If preexisting_names is None, the function falls back to a conservative behaviour:
          it will hide (not remove) any other layer with the same name.
        """
        try:
            final_name = getattr(final_layer, "name", display_name)

            for lyr in list(site_map.listLayers()):
                try:
                    # skip the final layer by name + longName check
                    if getattr(lyr, "name", "") == final_name:
                        try:
                            if getattr(lyr, "longName", "") == getattr(final_layer, "longName", ""):
                                continue
                        except Exception:
                            if lyr is final_layer:
                                continue

                    # Only consider layers that match the display_name
                    if getattr(lyr, "name", "") != display_name:
                        continue

                    # If we have a list of preexisting names, only remove layers that were present before we ran.
                    if preexisting_names is not None:
                        if display_name not in preexisting_names:
                            # Do not remove layers we did not previously have in the map
                            continue
                        # remove the layer that was preexisting (and matches the name)
                        try:
                            site_map.removeLayer(lyr)
                            arcpy.AddMessage(f"  • Removed pre-existing duplicate layer '{display_name}'.")
                        except Exception:
                            try:
                                lyr.visible = False
                            except Exception:
                                pass
                    else:
                        # Conservative fallback: don't delete — hide instead and log
                        try:
                            lyr.visible = False
                            arcpy.AddMessage(f"  • Hid duplicate layer '{display_name}' (conservative fallback).")
                        except Exception:
                            try:
                                site_map.removeLayer(lyr)
                                arcpy.AddMessage(f"  • Removed duplicate layer '{display_name}' (fallback).")
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

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

        # track a few summary bits for funky final message
        archived_count = 0
        appended_success = False
        matched_address = ""
        area_ha = 0.0

        # track temp paths created in this routine for cleanup
        created_temp_paths = set()
        removed_temp_paths = []
        failed_temp_deletes = []

        run_uuid = str(uuid.uuid4())[:8]

        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            default_gdb = aprx.defaultGeodatabase
            # record initial workspace so we can restore later if needed
            prior_workspace = None
            try:
                prior_workspace = arcpy.env.workspace
                arcpy.env.workspace = default_gdb
            except Exception:
                pass

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
            temp_geocoded = os.path.join("memory", f"geocoded_point_{run_uuid}")
            arcpy.management.CopyFeatures(geocoded_point, temp_geocoded)
            created_temp_paths.add(temp_geocoded)

            arcpy.AddMessage(f"Located at: {loc['x']:.5f}, {loc['y']:.5f}")

            # 2. Select property polygon (Cadastre)
            property_service_url = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer/12"

            temp_property_layer = f"temp_property_layer_{run_uuid}"
            arcpy.management.MakeFeatureLayer(property_service_url, temp_property_layer)

            arcpy.AddMessage("Selecting property parcel...")
            # first try strict CONTAINS
            arcpy.management.SelectLayerByLocation(temp_property_layer, "CONTAINS", temp_geocoded)
            property_count = int(arcpy.management.GetCount(temp_property_layer).getOutput(0))

            if property_count == 0:
                arcpy.AddMessage("  - No parcel selected with CONTAINS; trying INTERSECT with a small buffer around the geocoded point as a fallback...")

                try:
                    # get spatial reference of the cadastre layer
                    desc = arcpy.Describe(temp_property_layer)
                    layer_sr = getattr(desc, "spatialReference", None)

                    # create a copy of the geocoded point and project to the layer SR if needed
                    pt_in = os.path.join("memory", f"temp_geocode_copy_{run_uuid}")
                    if arcpy.Exists(pt_in):
                        try: arcpy.management.Delete(pt_in)
                        except: pass
                    arcpy.management.CopyFeatures(temp_geocoded, pt_in)
                    created_temp_paths.add(pt_in)

                    proj_pt = pt_in
                    if layer_sr and getattr(layer_sr, "factoryCode", None) and layer_sr.factoryCode != 4326:
                        # project into cadastre SR in memory
                        proj_pt = os.path.join("memory", f"temp_geocode_proj_{run_uuid}")
                        try:
                            if arcpy.Exists(proj_pt):
                                try: arcpy.management.Delete(proj_pt)
                                except: pass
                            arcpy.management.Project(pt_in, proj_pt, layer_sr)
                        except Exception:
                            # if project fails, continue with original pt_in
                            proj_pt = pt_in
                        created_temp_paths.add(proj_pt)

                    # buffer the point a small distance (2 metres) using GEODESIC for safety
                    buf_fc = os.path.join("memory", f"temp_geocode_buf_{run_uuid}")
                    if arcpy.Exists(buf_fc):
                        try: arcpy.management.Delete(buf_fc)
                        except: pass
                    arcpy.analysis.Buffer(proj_pt, buf_fc, "2 Meters", method="GEODESIC")
                    created_temp_paths.add(buf_fc)

                    # try INTERSECT using the small buffer
                    arcpy.management.SelectLayerByLocation(temp_property_layer, "INTERSECT", buf_fc)
                    property_count = int(arcpy.management.GetCount(temp_property_layer).getOutput(0))

                    # cleanup memory fcs (best-effort) - we'll clean up at the end too
                    try: arcpy.management.Delete(pt_in)
                    except: pass
                    try: arcpy.management.Delete(proj_pt)
                    except: pass
                    try: arcpy.management.Delete(buf_fc)
                    except: pass

                    if property_count == 0:
                        arcpy.AddError("No property polygon found at this location (NSW Cadastre) after fallback attempt.")
                        return
                    else:
                        arcpy.AddMessage(f"  ✓ Found {property_count} parcel(s) using buffer+INTERSECT fallback.")

                except Exception as e:
                    arcpy.AddWarning(f"  - Buffer/INTERSECT fallback failed: {e}")
                    arcpy.AddError("No property polygon found at this location (NSW Cadastre).")
                    return

            # Copy selection to local GDB
            temp_property = os.path.join(default_gdb, f"temp_property_{run_uuid}")
            if arcpy.Exists(temp_property):
                arcpy.management.Delete(temp_property)
            arcpy.management.CopyFeatures(temp_property_layer, temp_property)
            created_temp_paths.add(temp_property)

            try:
                arcpy.management.Delete(temp_property_layer)
            except:
                pass
            try:
                arcpy.management.Delete(temp_geocoded)
                if temp_geocoded in created_temp_paths:
                    created_temp_paths.discard(temp_geocoded)
                    removed_temp_paths.append(temp_geocoded)
            except:
                pass

            arcpy.management.RepairGeometry(temp_property, "DELETE_NULL")

            # Handle multi-polygon properties
            if property_count > 1:
                # Try dissolving in memory first to avoid file GDB locks
                dissolved_mem = os.path.join("in_memory", f"temp_dissolved_{run_uuid}")
                dissolved_gdb = os.path.join(default_gdb, f"temp_dissolved_{run_uuid}")
                try:
                    # ensure no leftover in memory
                    if arcpy.Exists(dissolved_mem):
                        try:
                            arcpy.management.Delete(dissolved_mem)
                        except:
                            pass

                    arcpy.AddMessage("  • Performing Dissolve in memory to avoid gdb locks...")
                    arcpy.management.Dissolve(temp_property, dissolved_mem, multi_part="MULTI_PART")

                    # Copy result back to default gdb so it persists for downstream processing
                    if arcpy.Exists(dissolved_gdb):
                        try:
                            arcpy.management.Delete(dissolved_gdb)
                        except:
                            pass
                    arcpy.management.CopyFeatures(dissolved_mem, dissolved_gdb)
                    created_temp_paths.add(dissolved_gdb)

                    # set working_fc to the persistent copy in the default gdb
                    working_fc = dissolved_gdb

                    # cleanup memory copy (best-effort)
                    try:
                        if arcpy.Exists(dissolved_mem):
                            arcpy.management.Delete(dissolved_mem)
                    except:
                        pass

                except arcpy.ExecuteError as ge:
                    # memory dissolve failed (maybe memory limitations or other). Try clearing workspace cache and do a file-gdb dissolve with a unique name.
                    arcpy.AddWarning(f"Memory Dissolve failed: {ge}\nAttempting alternative dissolve in default geodatabase.")
                    try:
                        arcpy.ClearWorkspaceCache_management()
                    except:
                        pass

                    # attempt a dissolve into a timestamped gdb FC to reduce name collisions/locks
                    alt_name = f"temp_dissolved_{int(time.time())}_{run_uuid}"
                    alt_dissolved = os.path.join(default_gdb, alt_name)
                    try:
                        arcpy.management.Dissolve(temp_property, alt_dissolved, multi_part="MULTI_PART")
                        working_fc = alt_dissolved
                        created_temp_paths.add(alt_dissolved)
                    except Exception as e2:
                        # If this still fails, surface a clear error for debugging
                        arcpy.AddError(f"Could not perform Dissolve (tried memory and file gdb): {e2}")
                        raise

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
                temp_target_layer = f"temp_target_layer_{run_uuid}"
                # Make a layer from the feature service (layer URL)
                arcpy.management.MakeFeatureLayer(target_layer_url, temp_target_layer)
                # Build a WHERE clause that respects the layer field types
                where_clause = build_project_defq(project_number, layer=temp_target_layer)
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
                        archived_count = existing_count
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
            try:
                arcpy.management.Append(working_fc, target_layer_url, "NO_TEST")
                appended_success = True
            except Exception as e:
                arcpy.AddError(f"Failed to append to feature service: {e}")
                appended_success = False

            # 5. Prefer authoritative service record for downstream processing and map display
            study_area_for_step2 = working_fc
            try:
                if appended_success:
                    # Create a temporary layer from the service and select the active feature for the project
                    temp_service_layer_name = f"temp_postappend_service_layer_{run_uuid}"
                    try:
                        if arcpy.Exists(temp_service_layer_name):
                            try:
                                arcpy.management.Delete(temp_service_layer_name)
                            except:
                                pass
                        arcpy.management.MakeFeatureLayer(target_layer_url, temp_service_layer_name)
                        where_clause = build_project_defq(project_number, layer=temp_service_layer_name)
                        arcpy.management.SelectLayerByAttribute(temp_service_layer_name, "NEW_SELECTION", where_clause)
                        sel_count = int(arcpy.management.GetCount(temp_service_layer_name).getOutput(0))
                        if sel_count > 0:
                            study_area_mem = os.path.join("memory", f"study_area_{project_number}_{run_uuid}")
                            if arcpy.Exists(study_area_mem):
                                try:
                                    arcpy.management.Delete(study_area_mem)
                                except:
                                    pass
                            arcpy.management.CopyFeatures(temp_service_layer_name, study_area_mem)
                            study_area_for_step2 = study_area_mem
                            created_temp_paths.add(study_area_mem)
                        else:
                            # Fallback: use local working_fc if we couldn't find the service record
                            study_area_for_step2 = working_fc
                    finally:
                        try:
                            arcpy.management.Delete(temp_service_layer_name)
                        except:
                            pass
            except Exception:
                # In case anything fails, fall back to working_fc
                study_area_for_step2 = working_fc

            # 6. Add to Map (No Zoom)
            try:
                map_obj = aprx.activeMap
                if map_obj:
                    # Prefer to add the feature service layer (authoritative) to the map so it stays connected to the service,
                    # rather than adding the temporary local table (temp_dissolved) which causes confusion / incorrect connections.
                    try:
                        # Attempt to add the service layer to the map (service URL)
                        psa_layer_added = None
                        if appended_success:
                            psa_layer_added = map_obj.addDataFromPath(target_layer_url)
                        else:
                            # Append failed - fall back to adding the local working_fc
                            psa_layer_added = map_obj.addDataFromPath(working_fc)

                        # Normalise returned object
                        top, child, parent = self._normalize_added(psa_layer_added)
                        psa_layer_obj = child or top
                        try:
                            psa_layer_obj.name = f"Project Study Area {project_number}"
                        except:
                            pass

                        # Attempt swap with LAYERFILE_PATH and ensure definition query is applied to the final layer
                        final_psa = None
                        if os.path.exists(LAYERFILE_PATH):
                            applied = False
                            # If we added the service layer, use its connectionProperties so the style points to the service
                            try:
                                if psa_layer_obj and getattr(psa_layer_obj, "connectionProperties", None):
                                    conn_source_layer = psa_layer_obj
                                else:
                                    # fallback: use the original data layer object if available
                                    conn_source_layer = psa_layer_obj

                                dq_for_psa = None
                                try:
                                    dq_for_psa = build_project_defq(project_number, layer=psa_layer_obj)
                                except:
                                    dq_for_psa = build_project_defq(project_number)

                                final = self._apply_style_swap(map_obj, psa_layer_obj, LAYERFILE_PATH, display_name=f"Project Study Area {project_number}", set_defq=dq_for_psa)
                                if final is not None:
                                    final_psa = final
                                    applied = True
                                    arcpy.AddMessage("  ✓ Applied standard Study Area symbology to PSA by swapping.")
                                else:
                                    # fallback to ApplySymbologyFromLayer on the data layer
                                    try:
                                        arcpy.management.ApplySymbologyFromLayer(psa_layer_obj, LAYERFILE_PATH)
                                        final_psa = psa_layer_obj
                                        applied = True
                                        arcpy.AddMessage("  ✓ Applied standard Study Area symbology using ApplySymbologyFromLayer.")
                                    except Exception as e_sym:
                                        arcpy.AddWarning(f"  - Could not apply standard symbology to Project Study Area: {e_sym}")
                            except Exception as e:
                                arcpy.AddWarning(f"  - Error while attempting to apply style to PSA: {e}")

                            # ensure definition query is applied using layer-aware builder
                            try:
                                if final_psa and final_psa.supports("DEFINITIONQUERY"):
                                    final_psa.definitionQuery = build_project_defq(project_number, layer=final_psa)
                                    arcpy.AddMessage("  ✓ Applied definition query to Project Study Area layer.")
                            except Exception:
                                pass
                        else:
                            arcpy.AddWarning("  - PSA layerfile not found; PSA added without standard styling.")

                    except Exception as e:
                        arcpy.AddWarning(f"Map update for PSA failed: {e}")
                else:
                    arcpy.AddWarning("No active map to add PSA.")
            except Exception as e:
                arcpy.AddWarning(f"Could not update map: {str(e)}")

            # After adding to service and map: perform stricter cleanup of temporary local copies that are purely transient
            try:
                arcpy.AddMessage("Cleaning up temporary data created during Step 1...")
                # Protect the study_area_for_step2 from deletion
                protected = set()
                try:
                    if study_area_for_step2:
                        protected.add(os.path.normpath(study_area_for_step2))
                except Exception:
                    pass

                for p in list(created_temp_paths):
                    try:
                        normp = os.path.normpath(p)
                    except Exception:
                        normp = p
                    if normp in protected:
                        continue
                    try:
                        if arcpy.Exists(p):
                            arcpy.management.Delete(p)
                            removed_temp_paths.append(p)
                        else:
                            # If it was an in-memory name already deleted earlier, still consider it removed
                            removed_temp_paths.append(p)
                    except Exception as delerr:
                        failed_temp_deletes.append({"path": p, "error": str(delerr)})
                        # continue cleaning other items
                        continue

                # Additionally: scan default gdb for loose temp FCs/tables matching known prefixes and remove them.
                prefixes = ("temp_", "tmp_extract_", "temp_dissolved_", "alt_dissolved_", f"temp_property_{run_uuid}", f"tmp_extract_")
                try:
                    prev_ws = arcpy.env.workspace
                    arcpy.env.workspace = default_gdb
                    # Feature classes
                    fc_list = arcpy.ListFeatureClasses() or []
                    for fc in fc_list:
                        try:
                            if any(fc.lower().startswith(pref.lower()) for pref in prefixes):
                                full = os.path.join(default_gdb, fc)
                                # don't delete protected path
                                if os.path.normpath(full) in protected:
                                    continue
                                try:
                                    arcpy.management.Delete(full)
                                    removed_temp_paths.append(full)
                                except Exception as e_del:
                                    failed_temp_deletes.append({"path": full, "error": str(e_del)})
                        except Exception:
                            pass
                    # Tables
                    tbls = arcpy.ListTables() or []
                    for tbl in tbls:
                        try:
                            if any(tbl.lower().startswith(pref.lower()) for pref in prefixes):
                                full = os.path.join(default_gdb, tbl)
                                if os.path.normpath(full) in protected:
                                    continue
                                try:
                                    arcpy.management.Delete(full)
                                    removed_temp_paths.append(full)
                                except Exception as e_del:
                                    failed_temp_deletes.append({"path": full, "error": str(e_del)})
                        except Exception:
                            pass
                except Exception:
                    pass
                finally:
                    try:
                        arcpy.env.workspace = prior_workspace
                    except Exception:
                        pass

                # Report cleanup results
                if removed_temp_paths:
                    arcpy.AddMessage("Temporary data removed:")
                    for r in removed_temp_paths:
                        arcpy.AddMessage(f"  - {r}")
                if failed_temp_deletes:
                    arcpy.AddWarning("Some temporary items could not be deleted (see details):")
                    for fi in failed_temp_deletes:
                        arcpy.AddWarning(f"  - {fi.get('path')}: {fi.get('error')}")
            except Exception as e:
                arcpy.AddWarning(f"Cleanup during Step 1 encountered errors: {e}")

            arcpy.AddMessage("\nSTEP 1 COMPLETE.")

            # Continue to Step 2 using the study area we just created if user requested it
            if run_step2_flag:
                arcpy.AddMessage("Proceeding to STEP 2 using the created study area...")
                try:
                    # Pass the in-memory copy of the appended service feature where possible so Step 2 operates on the authoritative geometry,
                    # and so the script is not accidentally connected to the temporary default-gdb table like temp_dissolved.
                    self._run_step2_with_study_area(aprx, study_area_for_step2, project_number, overwrite_flag, force_requery)
                except Exception as e:
                    arcpy.AddError(f"Error while running Step 2 after Step 1: {e}")
            else:
                arcpy.AddMessage("Step 2 was not requested to run automatically. Process completed after Step 1.")

            # Funky final messaging for Step 1
            arcpy.AddMessage("\n" + ("🎉" * 12))
            arcpy.AddMessage("FUNKY SUMMARY — STEP 1")
            arcpy.AddMessage("-" * 40)
            arcpy.AddMessage(f"Project: {project_number} — {project_name}")
            arcpy.AddMessage(f"Address used: {matched_address or 'N/A'}")
            arcpy.AddMessage(f"Site area: {area_ha:.2f} hectares")
            arcpy.AddMessage(f"Records archived on service: {archived_count}")
            arcpy.AddMessage(f"Appended to feature service: {'Yes' if appended_success else 'No'}")
            arcpy.AddMessage(f"Automatic STEP 2 run: {'Yes' if run_step2_flag else 'No'}")
            arcpy.AddMessage("-" * 40)
            arcpy.AddMessage("May the maps be ever in your favour. 🗺️")
            arcpy.AddMessage(("🎉" * 12) + "\n")

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

        def _sanitize_fc_name(name, max_len=63):
            """
            Produce a geodatabase-safe feature class name from an arbitrary display name:
            - replace any non-alphanumeric/underscore with underscore
            - collapse multiple underscores
            - strip leading/trailing underscores
            - prefix with 'f_' if it starts with a digit
            - truncate to max_len characters
            """
            if not name:
                return "layer"
            # replace invalid chars with underscore
            s = re.sub(r'[^0-9A-Za-z_]', '_', str(name))
            # collapse multiple underscores
            s = re.sub(r'_{2,}', '_', s)
            s = s.strip('_')
            if not s:
                s = "layer"
            # prefix if starts with digit
            if re.match(r'^\d', s):
                s = f"f_{s}"
            # truncate
            if len(s) > max_len:
                s = s[:max_len]
            return s

        reference_table_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15"
        arcpy.AddMessage("=" * 60)
        arcpy.AddMessage("STEP 2 - ADD PROJECT LAYERS (continuing from Step 1)")
        arcpy.AddMessage("=" * 60)

        # Summary trackers
        skipped = []
        extracted_new = []
        replaced = []
        failed = []
        # store fallback qurls (and error) for failed layers for post-run diagnostics
        fallback_qurls_for_failed = []

        # Track temporary items created by Step 2 for cleanup
        step2_created_temp = set()
        step2_removed = []
        step2_failed_deletes = []

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
            params = {"where": "ProjectType='all'", "outFields": "*", "f": "json", "orderByFields": "SortOrder ASC"}
            if token:
                params["token"] = token
            query_url = f"{reference_table_url}/query?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(query_url, timeout=60) as resp:
                ref_data = json.loads(resp.read().decode())

            features = ref_data.get("features", [])
            if not features:
                arcpy.AddWarning("No standard connections found for ProjectType = 'all'.")
            else:
                arcpy.AddMessage(f"  ✓ Found {len(features)} reference records (ordered by SortOrder).")

            processed_outputs = []  # track extracted layers for reports

            def _get_attr_ci(attrs, key):
                # case-insensitive attribute accessor
                for k, v in attrs.items():
                    if k.lower() == key.lower():
                        return v
                return None

            def _fetch_service_metadata(service_url, token=None):
                """
                Try a couple of sensible metadata endpoints for the given service URL and return a small dict
                with a few useful fields (if available). This is optional and best-effort.
                """
                try_urls = []
                base = service_url.rstrip('/')
                # if URL ends with a numeric layer id, also try the parent service endpoint
                try:
                    # parent service endpoint (strip trailing '/<id>' if present)
                    parent = base.rsplit('/', 1)[0]
                    try_urls.append(parent + '?f=json')
                except:
                    pass
                try_urls.append(base + '?f=json')

                for mu in try_urls:
                    murl = mu
                    if token:
                        sep = '&' if '?' in murl else '?'
                        murl = murl + f"&token={token}"
                    try:
                        with urllib.request.urlopen(murl, timeout=30) as mresp:
                            meta = json.loads(mresp.read().decode())
                            # collect a few helpful fields if present
                            info = {}
                            for k in ("serviceDescription", "name", "type", "currentVersion", "supportsQuery", "capabilities", "maxRecordCount"):
                                if k in meta:
                                    info[k] = meta[k]
                            if not info:
                                # fallback to top-level summary
                                info = {k: meta.get(k, "") for k in ("name", "type", "serviceDescription")}
                            return info
                    except Exception:
                        continue
                return None

            # Track whether we've created the Site Details Map in this run so we can add the study area first
            site_map_created_in_run = False

            # Find or create the "Site Details Map" once, before processing records.
            site_map = None
            maps = [m for m in aprx.listMaps() if m.name == "Site Details Map"]
            if maps:
                site_map = maps[0]
            else:
                try:
                    site_map = aprx.createMap("Site Details Map")
                    site_map_created_in_run = True
                    arcpy.AddMessage("  ✓ Created 'Site Details Map'.")
                    # Attempt to apply Imagery Hybrid basemap if the API supports it
                    try:
                        site_map.addBasemap("Imagery Hybrid")
                        arcpy.AddMessage("  ✓ Applied 'Imagery Hybrid' basemap to 'Site Details Map'.")
                    except Exception:
                        arcpy.AddWarning("  - Could not apply 'Imagery Hybrid' basemap programmatically; add it manually if required.")
                    # Attempt to set the map spatial reference to GDA2020 / NSW Lambert (8058) if supported
                    try:
                        site_map.spatialReference = arcpy.SpatialReference(8058)
                        arcpy.AddMessage("  ✓ Set 'Site Details Map' spatial reference to GDA2020 / NSW Lambert (8058).")
                    except Exception:
                        arcpy.AddWarning("  - Could not set spatial reference on 'Site Details Map' programmatically; layers will retain their own spatial references.")
                except Exception as cm_err:
                    arcpy.AddWarning(f"  - Could not create 'Site Details Map': {cm_err}")
                    site_map = None

            # Capture pre-existing layer names in the Site Details Map so we only remove pre-existing layers later
            preexisting_layer_names = set()
            try:
                if site_map:
                    preexisting_layer_names = {getattr(lyr, "name", "") for lyr in site_map.listLayers() if getattr(lyr, "name", "")}
            except Exception:
                preexisting_layer_names = set()

            # If we created the map just now, add the PSA first and style it (so it sits at root).
            if site_map_created_in_run and site_map:
                try:
                    psa_added = site_map.addDataFromPath(study_area_fc)
                    top_p, child_p, parent_p = self._normalize_added(psa_added)
                    psa_layer_obj = child_p or top_p
                    try:
                        psa_layer_obj.name = f"Project Study Area {project_number}"
                    except:
                        pass
                    final_psa_layer = psa_layer_obj
                    if os.path.exists(LAYERFILE_PATH):
                        final = self._apply_style_swap(site_map, psa_layer_obj, LAYERFILE_PATH, display_name=f"Project Study Area {project_number}", set_defq=build_project_defq(project_number, layer=psa_layer_obj))
                        if final:
                            final_psa_layer = final
                            arcpy.AddMessage("  ✓ Applied standard Study Area symbology to PSA by swapping.")
                        else:
                            try:
                                arcpy.management.ApplySymbologyFromLayer(psa_layer_obj, LAYERFILE_PATH)
                                final_psa_layer = psa_layer_obj
                                arcpy.AddMessage("  ✓ Applied standard Study Area symbology using ApplySymbologyFromLayer.")
                            except Exception as e_fall:
                                arcpy.AddWarning(f"  - PSA ApplySymbologyFromLayer fallback failed: {e_fall}")
                    try:
                        dq = build_project_defq(project_number, layer=final_psa_layer)
                        if final_psa_layer and final_psa_layer.supports("DEFINITIONQUERY"):
                            final_psa_layer.definitionQuery = dq
                            arcpy.AddMessage("  ✓ Applied definition query to Project Study Area layer.")
                    except Exception:
                        pass
                except Exception as eaddpsa:
                    arcpy.AddWarning(f"  - Could not add Project Study Area layer to 'Site Details Map': {eaddpsa}")
                # After initial PSA add, update preexisting names (PSA is now present but it's considered "new")
                try:
                    preexisting_layer_names = {getattr(lyr, "name", "") for lyr in site_map.listLayers() if getattr(lyr, "name", "")}
                except Exception:
                    pass

            # Process each reference record
            for idx, feat in enumerate(features, start=1):
                attrs = feat.get("attributes", {})
                service_url = _get_attr_ci(attrs, "URL") or _get_attr_ci(attrs, "Url") or _get_attr_ci(attrs, "url")
                site_buffer = _get_attr_ci(attrs, "SiteBuffer") or _get_attr_ci(attrs, "sitebuffer") or 0
                buffer_action = _get_attr_ci(attrs, "BufferAction") or _get_attr_ci(attrs, "bufferaction") or "INTERSECT"
                feature_dataset_name = _get_attr_ci(attrs, "FeatureDatasetName") or _get_attr_ci(attrs, "FeatureDataset") or "ProjectData"
                short_name = _get_attr_ci(attrs, "ShortName") or _get_attr_ci(attrs, "Shortname") or f"Layer_{idx}"
                style_file = _get_attr_ci(attrs, "Style") or _get_attr_ci(attrs, "LayerFile") or _get_attr_ci(attrs, "lyrx")

                # Normalize style_file: strip whitespace and surrounding quotes (some entries include them)
                raw_style_file = style_file
                if style_file:
                    try:
                        style_file = str(style_file).strip()
                        # strip surrounding single/double quotes if present
                        style_file = style_file.strip('\'"')
                        # normalize path separators
                        try:
                            style_file = os.path.normpath(style_file)
                        except Exception:
                            pass
                    except Exception:
                        pass
                if raw_style_file != style_file:
                    arcpy.AddMessage(f"  • Normalized style field: '{raw_style_file}' -> '{style_file or ''}'")

                # create a sanitized feature class name for use inside the geodatabase
                safe_short = _sanitize_fc_name(short_name)

                # Safe messaging: ensure None -> ''
                service_url_msg = service_url or ""
                style_file_msg = style_file or ""
                arcpy.AddMessage(f"Processing reference record {idx}: ShortName='{short_name}' (safe: '{safe_short}') URL='{service_url_msg}' Buffer={site_buffer} Action={buffer_action} Style='{style_file_msg}'")

                # Validate service URL
                if not service_url:
                    arcpy.AddWarning(f"  - No URL for reference record {short_name}; skipping.")
                    skipped.append(short_name)
                    continue

                # Basic service-type hint (MapServer or FeatureServer)
                try:
                    svc_type = None
                    if "/MapServer" in service_url:
                        svc_type = "MapServer"
                    elif "/FeatureServer" in service_url:
                        svc_type = "FeatureServer"
                    else:
                        svc_type = "UnknownServiceType"
                    arcpy.AddMessage(f"  • Service type hint: {svc_type}")
                except Exception:
                    pass

                # Build intended output path early (for quick existence check)
                fd_path = os.path.join(default_gdb, feature_dataset_name)
                out_fc = os.path.join(fd_path, safe_short)

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
                    buffer_fc = os.path.join("memory", f"buf_{safe_short}_{int(time.time())}")
                    if arcpy.Exists(buffer_fc):
                        arcpy.management.Delete(buffer_fc)
                    arcpy.analysis.Buffer(study_area_fc, buffer_fc, f"{distance_m} Meters", method="GEODESIC")
                    step2_created_temp.add(buffer_fc)
                else:
                    buffer_fc = study_area_fc

                # 2.2 Connect to the target feature layer and subset by buffer polygon
                temp_layer_name = f"temp_layer_{idx}_{int(time.time())}"
                made_layer = False
                try:
                    # Try the normal approach first
                    arcpy.management.MakeFeatureLayer(service_url, temp_layer_name)
                    made_layer = True
                    step2_created_temp.add(temp_layer_name)
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

                    # Fetch and print a little service metadata (best-effort) to help debugging
                    try:
                        meta = _fetch_service_metadata(service_url, token)
                        if meta:
                            arcpy.AddMessage(f"  • Service metadata (best-effort): {meta}")
                        else:
                            arcpy.AddMessage("  • No service metadata available (best-effort).")
                    except Exception:
                        pass

                    # Clean up any partially created layer
                    try:
                        if made_layer:
                            arcpy.management.Delete(temp_layer_name)
                            if temp_layer_name in step2_created_temp:
                                step2_created_temp.discard(temp_layer_name)
                    except:
                        pass

                    # REST fallback: query the service /query endpoint for OBJECTIDs intersecting the buffer geometry
                    try:
                        # get a single geometry JSON from buffer_fc (esri JSON) and determine its spatial reference
                        geom_json = None
                        geom_sr_wkid = 4326
                        with arcpy.da.SearchCursor(buffer_fc, ["SHAPE@"]) as gcur:
                            for grow in gcur:
                                geom_obj = grow[0]
                                try:
                                    geom_json = geom_obj.JSON
                                except:
                                    geom_json = None
                                # attempt to derive SR WKID from geometry JSON if present
                                try:
                                    if geom_json:
                                        gj = json.loads(geom_json)
                                        sr = gj.get("spatialReference") or {}
                                        geom_sr_wkid = sr.get("wkid") or sr.get("latestWkid") or geom_sr_wkid
                                except Exception:
                                    pass
                                # fallback to geometry object's spatialReference factoryCode/wkid
                                try:
                                    geom_sr_wkid = int(getattr(geom_obj.spatialReference, "factoryCode", getattr(geom_obj.spatialReference, "wkid", geom_sr_wkid)))
                                except Exception:
                                    pass
                                break

                        if not geom_json:
                            arcpy.AddWarning(f"  - Could not obtain geometry JSON for fallback on '{short_name}'.")
                            raise Exception("No geometry available for fallback query")

                        query_layer_url = service_url.rstrip('/') + "/query"
                        qparams = {
                            "geometry": geom_json,
                            "geometryType": "esriGeometryPolygon",
                            "spatialRel": "esriSpatialRelIntersects",
                            "inSR": str(geom_sr_wkid),
                            "returnIdsOnly": "true",
                            "f": "json"
                        }
                        if token:
                            qparams["token"] = token

                        # Retry loop for fallback query (attempt up to 3 times with backoff).
                        # If a 498 Invalid Token error is encountered, retry once without the token.
                        object_ids = []
                        last_err = None
                        qurl_used = None
                        attempt = 0
                        max_attempts = 3
                        tried_without_token = False

                        while attempt < max_attempts:
                            qurl = f"{query_layer_url}?{urllib.parse.urlencode(qparams)}"
                            qurl_used = qurl
                            arcpy.AddMessage(f"  - REST fallback query URL (attempt {attempt+1}{' (no token)' if tried_without_token else ''}): {qurl}")
                            try:
                                with urllib.request.urlopen(qurl, timeout=120) as qresp:
                                    qdata = json.loads(qresp.read().decode())
                                # check for REST error block
                                if "error" in qdata:
                                    last_err = qdata["error"]
                                    arcpy.AddWarning(f"  - REST fallback returned error: {last_err}")
                                    # If it's an invalid token error, retry once without token
                                    try:
                                        err_code = int(last_err.get("code", 0)) if isinstance(last_err, dict) else 0
                                    except Exception:
                                        err_code = 0
                                    if err_code == 498 and not tried_without_token:
                                        # remove token and retry immediately (do not consume one of the configured attempts)
                                        if "token" in qparams:
                                            qparams.pop("token", None)
                                        tried_without_token = True
                                        arcpy.AddMessage("  - Received 498 Invalid Token; retrying fallback without token.")
                                        # do not increment attempt here so we still allow up to max_attempts attempts without token
                                        continue
                                    # normal error; wait and retry
                                    attempt += 1
                                    time.sleep(3)
                                    continue

                                object_ids = qdata.get("objectIds") or []
                                # success if we got object ids (or empty list but query succeeded)
                                break

                            except Exception as e:
                                last_err = e
                                arcpy.AddWarning(f"  - REST fallback HTTP error on attempt {attempt+1}: {e}")
                                attempt += 1
                                time.sleep(3)

                        # store qurl for diagnostics if fallback produced no object ids
                        if not object_ids:
                            arcpy.AddMessage(f"  - REST query returned no features for '{short_name}'; skipping.")
                            failed.append(short_name)
                            # record the qurl and last error for post-run diagnostics
                            fallback_qurls_for_failed.append({"shortname": short_name, "qurl": qurl_used, "error": str(last_err)})
                            # ensure no leftover
                            try:
                                if arcpy.Exists(temp_layer_name):
                                    arcpy.management.Delete(temp_layer_name)
                                    if temp_layer_name in step2_created_temp:
                                        step2_created_temp.discard(temp_layer_name)
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
                            step2_created_temp.add(temp_layer_name)
                        except Exception as e2:
                            arcpy.AddWarning(f"  - Could not create filtered layer from service for '{short_name}': {e2}")
                            failed.append(short_name)
                            # ensure no leftover
                            try:
                                if arcpy.Exists(temp_layer_name):
                                    arcpy.management.Delete(temp_layer_name)
                                    if temp_layer_name in step2_created_temp:
                                        step2_created_temp.discard(temp_layer_name)
                            except:
                                pass
                            # record qurl for diagnostics
                            fallback_qurls_for_failed.append({"shortname": short_name, "qurl": qurl_used, "error": str(e2)})
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
                                if temp_layer_name in step2_created_temp:
                                    step2_created_temp.discard(temp_layer_name)
                        except:
                            pass
                        # record fallback info for diagnostics if available
                        try:
                            fallback_qurls_for_failed.append({"shortname": short_name, "qurl": qurl_used if 'qurl_used' in locals() else None, "error": str(fb_err)})
                        except:
                            pass
                        continue

                # At this point selection_succeeded indicates we have a usable temp_layer_name (either original selection or filtered layer)
                if not selection_succeeded:
                    arcpy.AddWarning(f"  - Could not select features for '{short_name}'; skipping.")
                    try:
                        if arcpy.Exists(temp_layer_name):
                            arcpy.management.Delete(temp_layer_name)
                            if temp_layer_name in step2_created_temp:
                                step2_created_temp.discard(temp_layer_name)
                    except:
                        pass
                    if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                        try:
                            arcpy.management.Delete(buffer_fc)
                            if buffer_fc in step2_created_temp:
                                step2_created_temp.discard(buffer_fc)
                        except:
                            pass
                    failed.append(short_name)
                    continue

                count = int(arcpy.management.GetCount(temp_layer_name).getOutput(0))
                arcpy.AddMessage(f"  - Selected {count} features from service.")

                if count < 1:
                    arcpy.AddMessage(f"  - No features selected for '{short_name}', skipping.")
                    try:
                        arcpy.management.Delete(temp_layer_name)
                        if temp_layer_name in step2_created_temp:
                            step2_created_temp.discard(temp_layer_name)
                    except:
                        pass
                    if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                        try:
                            arcpy.management.Delete(buffer_fc)
                            if buffer_fc in step2_created_temp:
                                step2_created_temp.discard(buffer_fc)
                        except:
                            pass
                    skipped.append(short_name)
                    continue

                # Ensure feature dataset exists in default GDB (create now, since we're going to write)
                if not arcpy.Exists(fd_path):
                    arcpy.AddMessage(f"  - Creating feature dataset '{feature_dataset_name}' in default geodatabase.")
                    arcpy.management.CreateFeatureDataset(default_gdb, feature_dataset_name, arcpy.SpatialReference(8058))

                # Write to a temporary output first (in default_gdb) then replace existing only on success
                timestamp = int(time.time())
                tmp_out = os.path.join(default_gdb, f"tmp_extract_{safe_short}_{timestamp}_{uuid.uuid4().hex[:6]}")
                try:
                    if buffer_action and buffer_action.strip().upper() == "CLIP":
                        # Clip to buffer -> write to tmp_out
                        arcpy.analysis.Clip(temp_layer_name, buffer_fc, tmp_out)
                    else:
                        # INTERSECT behavior: copy the selected features as-is to tmp_out
                        arcpy.management.CopyFeatures(temp_layer_name, tmp_out)
                    step2_created_temp.add(tmp_out)
                except Exception as e:
                    arcpy.AddWarning(f"  - Error extracting features for '{short_name}': {e}")
                    try:
                        arcpy.management.Delete(temp_layer_name)
                        if temp_layer_name in step2_created_temp:
                            step2_created_temp.discard(temp_layer_name)
                    except:
                        pass
                    if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                        try:
                            arcpy.management.Delete(buffer_fc)
                            if buffer_fc in step2_created_temp:
                                step2_created_temp.discard(buffer_fc)
                        except:
                            pass
                    failed.append(short_name)
                    # Clean up tmp_out if partially created
                    try:
                        if arcpy.Exists(tmp_out):
                            arcpy.management.Delete(tmp_out)
                            if tmp_out in step2_created_temp:
                                step2_created_temp.discard(tmp_out)
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
                                if tmp_out in step2_created_temp:
                                    step2_created_temp.discard(tmp_out)
                            except:
                                pass
                            failed.append(short_name)
                            try:
                                arcpy.management.Delete(temp_layer_name)
                                if temp_layer_name in step2_created_temp:
                                    step2_created_temp.discard(temp_layer_name)
                            except:
                                pass
                            if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                                try:
                                    arcpy.management.Delete(buffer_fc)
                                    if buffer_fc in step2_created_temp:
                                        step2_created_temp.discard(buffer_fc)
                                except:
                                    pass
                            continue

                        replaced.append(short_name)
                    else:
                        extracted_new.append(short_name)

                    # Move tmp_out to final location by copying features (ensures correct path/name inside FD)
                    arcpy.management.CopyFeatures(tmp_out, out_fc)
                    # Remove tmp_out
                    try:
                        arcpy.management.Delete(tmp_out)
                        if tmp_out in step2_created_temp:
                            step2_created_temp.discard(tmp_out)
                        step2_removed.append(tmp_out)
                    except:
                        pass

                    arcpy.AddMessage(f"  ✓ Extracted '{short_name}' to {out_fc}")
                    processed_outputs.append({"shortname": short_name, "path": out_fc, "style": style_file, "fd": feature_dataset_name, "safe_short": safe_short})

                    # Add the output layer to "Site Details Map" (root) and apply the style
                    try:
                        if site_map:
                            # Add data
                            data_added = site_map.addDataFromPath(out_fc)
                            top_added, added_child, parent_added = self._normalize_added(data_added)
                            data_layer = added_child or top_added
                            final_layer = data_layer
                            try:
                                data_layer.name = short_name
                            except Exception:
                                pass

                            # Attempt to apply style if provided
                            if style_file:
                                style_path = os.path.expanduser(style_file)
                                if not os.path.isabs(style_path):
                                    try_paths = [
                                        style_path,
                                        os.path.join(os.path.dirname(arcpy.mp.ArcGISProject("CURRENT").filePath or ""), style_path),
                                        os.path.join(default_gdb, style_path)
                                    ]
                                else:
                                    try_paths = [style_path]

                                applied = False
                                for sp in try_paths:
                                    try:
                                        arcpy.AddMessage(f"  - Checking style candidate: {sp} (exists: {os.path.exists(sp)})")
                                        if not os.path.exists(sp):
                                            continue

                                        # Try swap
                                        final = self._apply_style_swap(site_map, data_layer, sp, display_name=short_name)
                                        if final:
                                            final_layer = final
                                            applied = True
                                            arcpy.AddMessage(f"  ✓ Applied style from '{sp}' by swapping for '{short_name}'.")
                                            break
                                        else:
                                            # fallback to ApplySymbologyFromLayer
                                            try:
                                                arcpy.management.ApplySymbologyFromLayer(data_layer, sp)
                                                final_layer = data_layer
                                                applied = True
                                                arcpy.AddMessage(f"  ✓ Applied style from '{sp}' using ApplySymbologyFromLayer for '{short_name}'.")
                                                break
                                            except Exception as e_f:
                                                arcpy.AddWarning(f"  - ApplySymbologyFromLayer fallback also failed for '{sp}': {e_f}")
                                                try:
                                                    if parent_added:
                                                        site_map.removeLayer(parent_added)
                                                except:
                                                    pass
                                                continue
                                    except Exception:
                                        continue
                                if not applied:
                                    arcpy.AddMessage(f"  - No valid style file found or applied for '{short_name}' (checked {len(try_paths)} locations).")

                            # remove any duplicates that were pre-existing only
                            try:
                                self._cleanup_duplicates(site_map, final_layer, short_name, preexisting_names=preexisting_layer_names)
                            except Exception:
                                pass

                    except Exception as add_err:
                        arcpy.AddWarning(f"  - Could not add '{out_fc}' to 'Site Details Map': {add_err}")
                except Exception as e:
                    arcpy.AddWarning(f"  - Could not move temporary extract to final location for '{short_name}': {e}")
                    failed.append(short_name)
                    # attempt cleanup
                    try:
                        if arcpy.Exists(tmp_out):
                            arcpy.management.Delete(tmp_out)
                            if tmp_out in step2_created_temp:
                                step2_created_temp.discard(tmp_out)
                    except:
                        pass
                    try:
                        arcpy.management.Delete(temp_layer_name)
                        if temp_layer_name in step2_created_temp:
                            step2_created_temp.discard(temp_layer_name)
                    except:
                        pass
                    if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                        try:
                            arcpy.management.Delete(buffer_fc)
                            if buffer_fc in step2_created_temp:
                                step2_created_temp.discard(buffer_fc)
                        except:
                            pass
                    continue

                # cleanup per-record temporary items
                try:
                    if arcpy.Exists(temp_layer_name):
                        arcpy.management.Delete(temp_layer_name)
                        if temp_layer_name in step2_created_temp:
                            step2_created_temp.discard(temp_layer_name)
                    if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                        arcpy.management.Delete(buffer_fc)
                        if buffer_fc in step2_created_temp:
                            step2_created_temp.discard(buffer_fc)
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
                lots_layer = f"temp_lots_layer_{uuid.uuid4().hex[:6]}"
                try:
                    arcpy.management.MakeFeatureLayer(lots_fc, lots_layer)
                    step2_created_temp.add(lots_layer)
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
                        if arcpy.Exists(lots_layer):
                            arcpy.management.Delete(lots_layer)
                            if lots_layer in step2_created_temp:
                                step2_created_temp.discard(lots_layer)
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

            # Final summary of processing for QA (existing summary retained)
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

            # Post-run diagnostic: print fallback qurls used for failed layers (if any)
            if fallback_qurls_for_failed:
                arcpy.AddMessage("\nFallback REST queries used for failed layers (for debugging):")
                for item in fallback_qurls_for_failed:
                    arcpy.AddMessage(f"  - Layer: {item.get('shortname')}  |  qurl: {item.get('qurl')}  |  error: {item.get('error')}")
                arcpy.AddMessage("Tip: Copy the qurl into a browser or curl to inspect the service response.")

            # Step 2: stricter cleanup of temp items created during this step
            try:
                arcpy.AddMessage("Cleaning up temporary data created during Step 2...")
                # remove any in-memory or local temps we tracked
                for t in list(step2_created_temp):
                    try:
                        if arcpy.Exists(t):
                            arcpy.management.Delete(t)
                            step2_removed.append(t)
                        else:
                            # layer names may not be "exists" addressable; still consider them removed
                            step2_removed.append(t)
                    except Exception as e:
                        step2_failed_deletes.append({"path": t, "error": str(e)})
                        continue

                # Additionally remove leftovers in default_gdb with known prefixes (careful not to remove final outputs)
                prefixes = ("tmp_extract_", "temp_dissolved_", "temp_property_", "tmp_", "temp_")
                try:
                    prev_ws = arcpy.env.workspace
                    arcpy.env.workspace = default_gdb
                    fc_list = arcpy.ListFeatureClasses() or []
                    for fc in fc_list:
                        try:
                            if any(fc.lower().startswith(pref.lower()) for pref in prefixes):
                                full = os.path.join(default_gdb, fc)
                                # do not remove outputs we added
                                if any(full == po["path"] for po in processed_outputs):
                                    continue
                                try:
                                    arcpy.management.Delete(full)
                                    step2_removed.append(full)
                                except Exception as e_del:
                                    step2_failed_deletes.append({"path": full, "error": str(e_del)})
                        except Exception:
                            pass
                    tbls = arcpy.ListTables() or []
                    for tbl in tbls:
                        try:
                            if any(tbl.lower().startswith(pref.lower()) for pref in prefixes):
                                full = os.path.join(default_gdb, tbl)
                                try:
                                    arcpy.management.Delete(full)
                                    step2_removed.append(full)
                                except Exception as e_del:
                                    step2_failed_deletes.append({"path": full, "error": str(e_del)})
                        except Exception:
                            pass
                except Exception:
                    pass
                finally:
                    try:
                        arcpy.env.workspace = prev_ws
                    except Exception:
                        pass

                if step2_removed:
                    arcpy.AddMessage("Temporary data removed in Step 2:")
                    for r in step2_removed:
                        arcpy.AddMessage(f"  - {r}")
                if step2_failed_deletes:
                    arcpy.AddWarning("Some temporary items from Step 2 could not be deleted:")
                    for fi in step2_failed_deletes:
                        arcpy.AddWarning(f"  - {fi.get('path')}: {fi.get('error')}")
            except Exception as e:
                arcpy.AddWarning(f"Cleanup during Step 2 encountered errors: {e}")

            # FUNKY final summary block for Step 2
            arcpy.AddMessage("\n" + ("✨" * 12))
            arcpy.AddMessage("🌈 FUNKY FINAL REPORT — STEP 2 🌈")
            arcpy.AddMessage("-" * 50)
            arcpy.AddMessage(f"Project: {project_number}")
            arcpy.AddMessage(f"Total reference records attempted: {len(features)}")
            arcpy.AddMessage(f"New extractions: {len(extracted_new)}  |  Replacements: {len(replaced)}  |  Skipped: {len(skipped)}  |  Failed: {len(failed)}")
            arcpy.AddMessage("\nDetailed lists:")
            arcpy.AddMessage(f"  - Extracted: {extracted_new if extracted_new else 'None'}")
            arcpy.AddMessage(f"  - Replaced: {replaced if replaced else 'None'}")
            arcpy.AddMessage(f"  - Skipped: {skipped if skipped else 'None'}")
            arcpy.AddMessage(f"  - Failed: {failed if failed else 'None'}")
            arcpy.AddMessage("-" * 50)
            arcpy.AddMessage(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            arcpy.AddMessage("If anything failed, check warnings above and re-run with force re-query or enable overwrite as needed.")
            arcpy.AddMessage(("✨" * 12) + "\n")

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

        # Because we don't have a layer to inspect here (REST query), try numeric-unquoted first
        attempts = []
        if safe_project_number and safe_project_number.isdigit():
            attempts.append(f"project_number = {int(safe_project_number)} AND EndDate IS NULL")
        try:
            f = float(safe_project_number)
            if f.is_integer():
                attempts.append(f"project_number = {int(f)} AND EndDate IS NULL")
        except Exception:
            pass
        # always try quoted as final fallback
        attempts.append(f"project_number = '{safe_project_number}' AND EndDate IS NULL")

        query_result = None
        for where in attempts:
            params = {"where": where, "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json"}
            if token:
                params["token"] = token
            query_url = f"{target_layer_url}/query?{urllib.parse.urlencode(params)}"
            try:
                with urllib.request.urlopen(query_url, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
                if data.get("features"):
                    query_result = data
                    break
            except Exception:
                # try next form
                continue

        if not query_result:
            return None

        feat = query_result['features'][0]
        sr = query_result.get('spatialReference') or {"wkid": 4326}
        polygon = arcpy.AsShape({"rings": feat['geometry']['rings'], "spatialReference": sr}, True)

        temp_fc = os.path.join("memory", f"study_area_{project_number}_{uuid.uuid4().hex[:6]}")
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

            # Add a small funky ending for standalone Step 2
            arcpy.AddMessage("\n🎈🎈🎈 Standalone STEP 2 complete — party time! 🎈🎈🎈")
            arcpy.AddMessage(f"Project {project_number}: standard layers added (see messages above for details).")
            arcpy.AddMessage("Tip: Re-run with 'Force re-query' or 'Overwrite' if you expected different results.\n")

            arcpy.AddMessage("\nSUCCESS - Project Layers Added.")

        except Exception as e:
            arcpy.AddError(f"Error executing Step 2: {str(e)}")
            import traceback
            arcpy.AddError(traceback.format_exc())
        return
