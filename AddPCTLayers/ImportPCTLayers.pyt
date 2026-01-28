import arcpy
import os
import re
import random
import time
import urllib.parse
import urllib.request
import json
import ssl

class Toolbox(object):
    def __init__(self):
        self.label = "Project Creation Toolbox"
        self.alias = "project_creation"
        self.tools = [ImportPCTLayerTool]

class ImportPCTLayerTool(object):
    def __init__(self):
        self.label = "Import Standard Site Layers"
        self.description = "Imports site layers, extracts styling, and saves .lyrx files."
        self.canRunInBackground = False

    def getParameterInfo(self):
        # Param 0: Project Number
        param0 = arcpy.Parameter(
            displayName="Project Number (choose Study Area)",
            name="project_number",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
       
        param0.filter.type = "ValueList"
        param0.filter.list = [] 

        # Param 1: Overwrite
        param1 = arcpy.Parameter(
            displayName="Overwrite existing project data",
            name="overwrite_existing",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param1.value = False

        # Param 2: Refresh
        param2 = arcpy.Parameter(
            displayName="Force re-query even if output exists (refresh)",
            name="force_refresh",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param2.value = False

        return [param0, param1, param2]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        p_project = parameters[0]
        if not p_project.filter.list:
            service_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"
            try:
                unique_projects = set()
                with arcpy.da.SearchCursor(service_url, ["project_number"], where_clause="1=1") as cursor:
                    for row in cursor:
                        if row[0]: unique_projects.add(str(row[0]))
                p_project.filter.list = sorted(list(unique_projects)) if unique_projects else ["No Projects Found"]
            except Exception as e:
                p_project.filter.list = [f"ERROR: {str(e)[:100]}"]
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        p_number = parameters[0].valueAsText
        p_overwrite = parameters[1].value
        p_refresh = parameters[2].value
        
        if "ERROR" in p_number or "Found" in p_number:
            messages.addErrorMessage("Please select a valid Project Number.")
            return

        run_import_std_site_layers(p_number, p_overwrite, p_refresh)
        return

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def sanitize_name(name):
    if not name: return "Unknown_Layer"
    clean = re.sub(r'[\s\-]+', '_', name)
    clean = re.sub(r'[^a-zA-Z0-9_]', '', clean)
    return clean

def get_random_dad_joke():
    jokes = [
        "Why did the map go to the doctor? It had a bad case of projection!",
        "What do you call a map guide to Alcatraz? A con-tour map.",
        "Why does the Prime Meridian feel superior? It knows its place.",
        "What kind of maps do spiders make? Web maps!",
        "Why did the dot go to college? To become a point of interest."
    ]
    return random.choice(jokes)

def get_object_ids_via_rest(service_url, geometry_provider, token=None):
    """
    Queries the REST endpoint directly for ObjectIDs with Smart Token Retry logic.
    """
    try:
        desc = arcpy.Describe(geometry_provider)
        extent = desc.extent
        sr_code = desc.spatialReference.factoryCode
        
        query_url = f"{service_url}/query"
        base_params = {
            'f': 'json',
            'returnIdsOnly': 'true',
            'geometry': f"{extent.XMin},{extent.YMin},{extent.XMax},{extent.YMax}",
            'geometryType': 'esriGeometryEnvelope',
            'spatialRel': 'esriSpatialRelIntersects',
            'inSR': sr_code
        }
        
        def send_request(params):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            data = urllib.parse.urlencode(params).encode('utf-8')
            req = urllib.request.Request(query_url, data)
            with urllib.request.urlopen(req, context=ctx) as response:
                return json.loads(response.read().decode('utf-8'))

        result = None
        # Attempt A: With Token
        if token:
            params = base_params.copy()
            params['token'] = token
            result = send_request(params)
            if 'error' in result and result['error']['code'] in [498, 499]:
                arcpy.AddMessage("    (Token rejected by server. Retrying as anonymous request...)")
                result = None 
        
        # Attempt B: Without Token
        if result is None:
            params = base_params.copy() 
            result = send_request(params)
            
        if 'error' in result:
            arcpy.AddWarning(f"    Rest API Error: {result['error']}")
            return []
            
        return result.get('objectIds', [])
    except Exception as e:
        arcpy.AddWarning(f"    Failed to query IDs via REST: {e}")
        return []

# -----------------------------------------------------------------------------
# LOGIC FUNCTION
# -----------------------------------------------------------------------------
def run_import_std_site_layers(project_number, overwrite_existing, force_refresh):
    
    # 1. CONFIGURATION
    ref_table_path = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15"
    psa_service_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"
    target_sr = arcpy.SpatialReference(8058) 

    # Auth
    agol_token = None
    try:
        token_info = arcpy.GetSigninToken()
        if token_info: agol_token = token_info.get('token')
    except: pass 

    # DB Location
    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        target_gdb = aprx.defaultGeodatabase
        project_home = aprx.homeFolder
    except:
        target_gdb = arcpy.env.workspace
        project_home = os.path.dirname(target_gdb)
    
    # Create "Layers" folder next to GDB for the .lyrx files
    layers_output_folder = os.path.join(project_home, "Layers")
    if not os.path.exists(layers_output_folder):
        try: os.makedirs(layers_output_folder)
        except: layers_output_folder = project_home # Fallback

    arcpy.env.overwriteOutput = True
    
    # Check License
    license_level = arcpy.ProductInfo()
    can_alter_alias = True
    if license_level == 'ArcView': can_alter_alias = False

    arcpy.AddMessage("============================================================")
    arcpy.AddMessage("STEP 4 - ADD PCT LAYERS (Symbology Edition)")
    arcpy.AddMessage("============================================================")
    
    # 2. GET PROJECT STUDY AREA
    arcpy.AddMessage(f"🔍 Hunting down study area for Project {project_number}...")
    psa_layer = "lyr_project_study_area"
    if arcpy.Exists(psa_layer): arcpy.management.Delete(psa_layer)
    arcpy.management.MakeFeatureLayer(psa_service_url, psa_layer)
    
    try:
        arcpy.management.SelectLayerByAttribute(psa_layer, "NEW_SELECTION", f"project_number = '{project_number}'")
    except:
        arcpy.management.SelectLayerByAttribute(psa_layer, "NEW_SELECTION", f"project_number = {project_number}")
    
    if int(arcpy.management.GetCount(psa_layer)[0]) == 0:
        arcpy.AddError(f"CRITICAL: Project {project_number} not found.")
        return

    # 3. READ REFERENCE TABLE
    arcpy.AddMessage("📖 Reading the sacred scrolls (Reference Table)...")
    layers_to_process = []
    
    fields = ['ShortName', 'URL', 'SiteBuffer', 'SortOrder', 'FeatureDatasetName', 'FieldAlias']
    try:
        with arcpy.da.SearchCursor(ref_table_path, fields, where_clause="ProjectType = 'pct'", sql_clause=(None, "ORDER BY SortOrder")) as cursor:
            for row in cursor:
                layers_to_process.append({
                    'name': row[0],
                    'source': row[1],
                    'buffer': 0 if row[2] is None else int(row[2]),
                    'dataset': row[4],
                    'alias': row[5]
                })
        arcpy.AddMessage(f"  ✓ Found {len(layers_to_process)} layers.")
    except Exception as e:
        arcpy.AddError(f"FAILED to read Reference Table: {e}")
        return

    # 4. PROCESSING LOOP
    stats = {'new': 0, 'skipped': 0, 'failed': 0}
    
    clip_boundary_fc = r"memory\primary_clip_boundary"
    if arcpy.Exists(clip_boundary_fc): arcpy.management.Delete(clip_boundary_fc)
    arcpy.management.CopyFeatures(psa_layer, clip_boundary_fc)

    for i, item in enumerate(layers_to_process, 1):
        raw_name = item['name']
        name = sanitize_name(raw_name)
        source_url = item['source']
        buff_dist = item['buffer']
        fd_name = item['dataset']
        table_alias = item['alias']
        
        # Output Paths
        target_container = target_gdb
        if fd_name:
            fd_clean = sanitize_name(fd_name)
            fd_path = os.path.join(target_gdb, fd_clean)
            if not arcpy.Exists(fd_path):
                try: arcpy.management.CreateFeatureDataset(target_gdb, fd_clean, target_sr)
                except: fd_path = target_gdb
            target_container = fd_path
            
        output_fc = os.path.join(target_container, name)
        
        arcpy.AddMessage(f"Processing {i}: {name} (Buffer: {buff_dist}m)")

        if arcpy.Exists(output_fc) and not overwrite_existing and not force_refresh:
            arcpy.AddMessage(f"  • Already there! (Skipped)")
            stats['skipped'] += 1
            continue
        elif arcpy.Exists(output_fc):
            arcpy.AddMessage(f"  • Overwriting...")

        if not source_url:
            stats['failed'] += 1
            continue

        try:
            # A. PREPARE GEOMETRY
            current_query_geom = r"memory\query_geom"
            if arcpy.Exists(current_query_geom): arcpy.management.Delete(current_query_geom)

            if buff_dist > 0:
                arcpy.analysis.Buffer(clip_boundary_fc, current_query_geom, f"{buff_dist} Meters")
            else:
                arcpy.management.CopyFeatures(clip_boundary_fc, current_query_geom)

            # B. ID FETCH -> BATCH -> RESCUE
            arcpy.AddMessage("  • Step 1: Querying Service IDs...")
            object_ids = get_object_ids_via_rest(source_url, current_query_geom, agol_token)
            
            if not object_ids:
                arcpy.AddMessage("  • No features intersect bounding box.")
                stats['skipped'] += 1
                continue

            arcpy.AddMessage(f"  • Found {len(object_ids)} candidate features.")
            BATCH_SIZE = 20 
            
            # Determine OID Field
            try:
                temp_desc = "probe_layer"
                arcpy.management.MakeFeatureLayer(source_url, temp_desc, "1=0")
                oid_field = arcpy.Describe(temp_desc).OIDFieldName
                arcpy.management.Delete(temp_desc)
            except: oid_field = "OBJECTID"

            arcpy.AddMessage(f"  • Step 2: Downloading...")
            merged_memory_fc = r"memory\merged_download"
            if arcpy.Exists(merged_memory_fc): arcpy.management.Delete(merged_memory_fc)
            
            chunks = [object_ids[x:x+BATCH_SIZE] for x in range(0, len(object_ids), BATCH_SIZE)]
            
            for index, chunk in enumerate(chunks):
                ids_str = ",".join(map(str, chunk))
                where_clause = f"{oid_field} IN ({ids_str})"
                chunk_layer = "chunk_layer"
                if arcpy.Exists(chunk_layer): arcpy.management.Delete(chunk_layer)
                
                try:
                    arcpy.management.MakeFeatureLayer(source_url, chunk_layer, where_clause)
                    chunk_fc = f"memory\\chunk_{index}"
                    arcpy.management.CopyFeatures(chunk_layer, chunk_fc)
                    
                    if not arcpy.Exists(merged_memory_fc):
                        arcpy.management.CopyFeatures(chunk_fc, merged_memory_fc)
                    else:
                        arcpy.management.Append(chunk_fc, merged_memory_fc, "NO_TEST")
                    arcpy.management.Delete(chunk_fc)
                    
                except Exception as batch_err:
                    arcpy.AddWarning(f"    ! Batch {index+1} failed. Activating Single-Feature Rescue Mode...")
                    for single_id in chunk:
                        try:
                            res_lyr = "res_lyr"
                            if arcpy.Exists(res_lyr): arcpy.management.Delete(res_lyr)
                            arcpy.management.MakeFeatureLayer(source_url, res_lyr, f"{oid_field} = {single_id}")
                            res_fc = f"memory\\res_{single_id}"
                            arcpy.management.CopyFeatures(res_lyr, res_fc)
                            if not arcpy.Exists(merged_memory_fc): arcpy.management.CopyFeatures(res_fc, merged_memory_fc)
                            else: arcpy.management.Append(res_fc, merged_memory_fc, "NO_TEST")
                            for x in [res_lyr, res_fc]: arcpy.management.Delete(x)
                        except: pass
                
                if arcpy.Exists(chunk_layer): arcpy.management.Delete(chunk_layer)
                time.sleep(0.1)

            # C. FINAL SAVE & SYMBOLOGY
            if arcpy.Exists(merged_memory_fc):
                arcpy.AddMessage("  • Step 3: Hard Clip & Save...")
                arcpy.analysis.Clip(merged_memory_fc, current_query_geom, output_fc)
                final_count = int(arcpy.management.GetCount(output_fc)[0])
                arcpy.AddMessage(f"  ✓ Saved {final_count} features.")

                # --- SYMBOLOGY EXTRACTION START ---
                try:
                    arcpy.AddMessage("  • Extracting symbology to .lyrx file...")
                    
                    # 1. Create a layer from the Service URL (this holds the styling)
                    temp_service_style = "temp_service_style"
                    if arcpy.Exists(temp_service_style): arcpy.management.Delete(temp_service_style)
                    arcpy.management.MakeFeatureLayer(source_url, temp_service_style)
                    
                    # 2. Create a layer from our new Local Data
                    temp_local_lyr = f"lyr_{name}"
                    if arcpy.Exists(temp_local_lyr): arcpy.management.Delete(temp_local_lyr)
                    arcpy.management.MakeFeatureLayer(output_fc, temp_local_lyr)
                    
                    # 3. Transfer Symbology (Service -> Local)
                    arcpy.management.ApplySymbologyFromLayer(temp_local_lyr, temp_service_style)
                    
                    # 4. Save to .lyrx
                    lyrx_path = os.path.join(layers_output_folder, f"{name}.lyrx")
                    arcpy.management.SaveToLayerFile(temp_local_lyr, lyrx_path, "RELATIVE")
                    
                    arcpy.AddMessage(f"  ✓ Created layer file: {os.path.basename(lyrx_path)}")
                    
                    # Cleanup
                    arcpy.management.Delete(temp_service_style)
                    arcpy.management.Delete(temp_local_lyr)
                except Exception as sym_e:
                    arcpy.AddWarning(f"  ! Symbology extraction failed: {sym_e}")
                # --- SYMBOLOGY EXTRACTION END ---

                # Alias Logic
                if can_alter_alias and table_alias:
                    try: arcpy.management.AlterAliasName(output_fc, table_alias)
                    except: pass
                
                stats['new'] += 1
                arcpy.management.Delete(merged_memory_fc)
            else:
                arcpy.AddWarning("  ! Failed to download any batches.")
                stats['failed'] += 1

            if arcpy.Exists(current_query_geom): arcpy.management.Delete(current_query_geom)

        except Exception as e:
            arcpy.AddWarning(f"  ! ERROR: {str(e)}")
            stats['failed'] += 1

    # 5. SUMMARY
    arcpy.AddMessage("\n✨✨✨✨✨✨✨✨✨✨✨✨")
    arcpy.AddMessage("MISCHIEF MANAGED (Summary)")
    arcpy.AddMessage(f"Captured: {stats['new']} | Ignored: {stats['skipped']} | Exploded: {stats['failed']}")
    arcpy.AddMessage(f"Layer files saved to: {layers_output_folder}")
    arcpy.AddMessage("--------------------------------------------------")
