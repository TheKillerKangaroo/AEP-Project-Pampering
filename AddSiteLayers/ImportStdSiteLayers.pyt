import arcpy
import os
import re
import random
import time

class Toolbox(object):
    def __init__(self):
        self.label = "Project Creation Toolbox"
        self.alias = "project_creation"
        self.tools = [ImportStdSiteLayersTool]

class ImportStdSiteLayersTool(object):
    def __init__(self):
        self.label = "Import Standard Site Layers"
        self.description = "Imports site layers using AGOL Project Areas and Reference Table (Funky Edition)."
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
        "Why did the dot go to college? To become a point of interest.",
        "I have a map of the US... actual size. It says '1 mile = 1 mile'. It's a nightmare to fold.",
        "Where do map makers go when they die? The Legend.",
        "Why don't GDBs ever get lost? They always have good topology.",
        "Buffer complete. Time for a coffee break? Just kidding, keep working.",
        "What do you call a map that smells? A scent-sus tract."
    ]
    return random.choice(jokes)

# -----------------------------------------------------------------------------
# LOGIC FUNCTION
# -----------------------------------------------------------------------------
def run_import_std_site_layers(project_number, overwrite_existing, force_refresh):
    
    # 1. CONFIGURATION
    ref_table_path = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15"
    psa_service_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"
    target_sr = arcpy.SpatialReference(8058) # GDA2020 NSW Lambert

    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        target_gdb = aprx.defaultGeodatabase
    except:
        target_gdb = arcpy.env.workspace
    
    arcpy.env.overwriteOutput = True
    
    # CHECK LICENSE LEVEL
    license_level = arcpy.ProductInfo()
    can_alter_alias = True
    if license_level == 'ArcView': # ArcView = Basic License
        can_alter_alias = False

    arcpy.AddMessage("============================================================")
    arcpy.AddMessage("STEP 2 - ADD PROJECT LAYERS (Funky Edition 🕺)")
    arcpy.AddMessage("============================================================")
    arcpy.AddMessage(f"License Level: {license_level}")
    if not can_alter_alias:
        arcpy.AddMessage("Note: Basic License detected. Skipping Alias renaming to avoid errors.")
        
    arcpy.AddMessage(f"Tip: {get_random_dad_joke()}")

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
        arcpy.AddError(f"CRITICAL: Project {project_number} is playing hide and seek (and winning). Not found.")
        return

    # 3. READ REFERENCE TABLE
    arcpy.AddMessage("📖 Reading the sacred scrolls (Reference Table)...")
    layers_to_process = []
    
    fields = ['ShortName', 'URL', 'SiteBuffer', 'SortOrder', 'FeatureDatasetName', 'FieldAlias']
    
    try:
        with arcpy.da.SearchCursor(ref_table_path, fields, where_clause="ProjectType = 'all'", sql_clause=(None, "ORDER BY SortOrder")) as cursor:
            for row in cursor:
                layers_to_process.append({
                    'name': row[0],
                    'source': row[1],
                    'buffer': 0 if row[2] is None else int(row[2]),
                    'dataset': row[4],
                    'alias': row[5]
                })
        arcpy.AddMessage(f"  ✓ Found {len(layers_to_process)} layers to wrangle.")
    except Exception as e:
        arcpy.AddError(f"FAILED to read Reference Table: {e}")
        return

    # 4. PROCESSING LOOP
    stats = {'new': 0, 'skipped': 0, 'failed': 0}
    
    clip_boundary_fc = r"memory\primary_clip_boundary"
    if arcpy.Exists(clip_boundary_fc): arcpy.management.Delete(clip_boundary_fc)
    arcpy.management.CopyFeatures(psa_layer, clip_boundary_fc)

    for i, item in enumerate(layers_to_process, 1):
        if i % 5 == 0:
             arcpy.AddMessage(f"---- ☕ {get_random_dad_joke()} ☕ ----")

        raw_name = item['name']
        name = sanitize_name(raw_name)
        source_url = item['source']
        buff_dist = item['buffer']
        fd_name = item['dataset']
        table_alias = item['alias']
        
        target_container = target_gdb
        if fd_name:
            fd_clean = sanitize_name(fd_name)
            fd_path = os.path.join(target_gdb, fd_clean)
            if not arcpy.Exists(fd_path):
                arcpy.AddMessage(f"  • Birthing new Feature Dataset: {fd_clean}")
                try:
                    arcpy.management.CreateFeatureDataset(target_gdb, fd_clean, target_sr)
                except:
                    fd_path = target_gdb
            target_container = fd_path
            
        output_fc = os.path.join(target_container, name)
        
        arcpy.AddMessage(f"Processing {i}: {name} (Buffer: {buff_dist}m)")

        if arcpy.Exists(output_fc):
            if not overwrite_existing and not force_refresh:
                arcpy.AddMessage(f"  • Already there! (Skipped like a rock on a lake)")
                stats['skipped'] += 1
                continue
            else:
                arcpy.AddMessage(f"  • Nuking existing layer and rewriting...")

        if not source_url:
            stats['failed'] += 1
            continue

        try:
            current_clip_geom = r"memory\current_clip_geom"
            if arcpy.Exists(current_clip_geom): arcpy.management.Delete(current_clip_geom)

            if buff_dist > 0:
                arcpy.analysis.Buffer(clip_boundary_fc, current_clip_geom, f"{buff_dist} Meters")
            else:
                arcpy.management.CopyFeatures(clip_boundary_fc, current_clip_geom)

            temp_layer = "temp_service_layer"
            if arcpy.Exists(temp_layer): arcpy.management.Delete(temp_layer)
            arcpy.management.MakeFeatureLayer(source_url, temp_layer)

            # Soft Clip
            arcpy.management.SelectLayerByLocation(temp_layer, "INTERSECT", current_clip_geom)
            
            match_count = int(arcpy.management.GetCount(temp_layer)[0])
            
            if match_count == 0:
                arcpy.AddMessage("  • Ghost town. No features found here.")
                stats['skipped'] += 1
            else:
                # Download
                temp_local_download = r"memory\temp_download"
                if arcpy.Exists(temp_local_download): arcpy.management.Delete(temp_local_download)
                arcpy.management.CopyFeatures(temp_layer, temp_local_download)

                # Hard Clip
                arcpy.analysis.Clip(temp_local_download, current_clip_geom, output_fc)
                
                final_count = int(arcpy.management.GetCount(output_fc)[0])
                arcpy.AddMessage(f"  ✓ Snagged {final_count} features.")
                
                # --- ALIAS LOGIC (LICENSE AWARE) ---
                if can_alter_alias and table_alias:
                    applied = False
                    attempts = 0
                    while not applied and attempts < 3:
                        try:
                            # Use standard syntax now that we know we have a license
                            arcpy.management.AlterAliasName(output_fc, table_alias)
                            applied = True
                        except Exception as alias_e:
                            attempts += 1
                            time.sleep(1) 
                elif table_alias and not can_alter_alias:
                    # Silent skip or minimal debug msg
                    pass 
                
                stats['new'] += 1

            for item in [current_clip_geom, temp_local_download]:
                if arcpy.Exists(item): arcpy.management.Delete(item)

        except Exception as e:
            if "999999" in str(e) or "000117" in str(e):
                 arcpy.AddWarning(f"  ! Warning: Geometry gremlins ate the output.")
            else:
                arcpy.AddWarning(f"  ! ERROR: {str(e)}")
            stats['failed'] += 1

    # 5. SUMMARY
    arcpy.AddMessage("\n✨✨✨✨✨✨✨✨✨✨✨✨")
    arcpy.AddMessage("MISCHIEF MANAGED (Summary)")
    arcpy.AddMessage(f"Project: {project_number}")
    arcpy.AddMessage(f"Captured: {stats['new']} | Ignored: {stats['skipped']} | Exploded: {stats['failed']}")
    arcpy.AddMessage("--------------------------------------------------")
