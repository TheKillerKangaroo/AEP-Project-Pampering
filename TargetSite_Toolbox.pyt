import arcpy
import requests
import json
import os
import sys
import datetime
import shutil
import subprocess

# --- GLOBAL CONSTANTS ---
# Cadastre Service URLs
FEATURE_PARCEL_LAYER_URL = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer/8"
FEATURE_SERVICE_URL = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer"
# Flora MapServer URL (Vegetation)
FLORA_MAP_SERVICE_URL = "https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/VIS/SVTM_NSW_Extant_PCT/MapServer" 
# Planning MapServer URL (Zoning)
PLANNING_MAP_SERVICE_URL = "https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/Planning/Principal_Planning_Layers/MapServer" 
# Bushfire Prone Land FeatureServer URL (NEW)
BUSHFIRE_PRONE_LAND_URL = "https://portal.spatial.nsw.gov.au/server/rest/services/Hosted/NSW_BushFire_Prone_Land/FeatureServer/0"
# *** NEW CONSTANT for Administrative Boundaries ***
ADMIN_BOUNDARIES_SERVICE_URL = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Administrative_Boundaries_Theme/FeatureServer"

# --- HELPER FUNCTION: POPULATE ADMIN BOUNDARIES LAYERS ---
def populate_admin_boundaries_from_service(gdb_path, buffer_path, feature_service_url):        
    """
    Clips all layers in the NSW Administrative Boundaries Theme service to the site buffer,
    saves them to the 'AdminBoundaries' feature dataset, and adds/populates 
    an 'Extract_date' field.
    """
    arcpy.AddMessage("\n--- COMRADE! Begin ADMINISTRATIVE EXTRACTION! Must conquer all boundaries! ---")
            
    # 1. Get the Service JSON to find all layers
    try:
        response = requests.get(feature_service_url + '?f=json', timeout=15)
        response.raise_for_status()
        service_data = response.json()
    except requests.exceptions.RequestException as e:
        arcpy.AddError(f"NYET! Feature Service URL: {feature_service_url} is FAILING ME! IT IS TREASON! Error: {e}") 
        return False
                
    layers = service_data.get('layers', [])
            
    if not layers:
        arcpy.AddWarning("DA? Metadata says NYET layers! Service is EMPTY like Gulag ration. Warning.")
        return False

    admin_ds_path = os.path.join(gdb_path, 'AdminBoundaries')
    if not arcpy.Exists(admin_ds_path):                
        arcpy.AddWarning(f"AdminBoundaries Feature Dataset not found at: {admin_ds_path}. Skipping population. This is UNACCEPTABLE.")                
        return False
                    
    arcpy.AddMessage(f"""We have captured {len(layers)} administrative layers for Motherland!
Prepare for geographic SUBTRACTION...""")
    success_count = 0
            
    # 2. Loop through each layer
    for layer in layers:
        layer_id = layer['id']
        layer_raw_name = layer['name']
                                
        # --- Use arcpy.ValidateTableName for robust naming ---        
        base_name = f"T{layer_id}_{layer_raw_name}"                      
        try:
            validated_name = arcpy.ValidateTableName(base_name, admin_ds_path)                 
        except Exception as name_e:
            arcpy.AddWarning(f"""   --> FAILED to validate name for 
layer {layer_raw_name}. Skipping. Error: {name_e}. Must work harder next time!""")
            continue
                                
        output_fc_path = os.path.join(admin_ds_path, validated_name)                  
        if arcpy.Exists(output_fc_path):                         
            arcpy.AddWarning(f" - Layer {layer_raw_name} already exists. Skipping. Efficiency is for the WEAK!")
            success_count += 1                         
            continue
                                
        arcpy.AddMessage(f""" - Processing Layer {layer_id}: {layer_raw_name} (Save to Geodatabase as: {validated_name}).
GO! GO! GO!""")
                        
        try:
            layer_url = f"{feature_service_url}/{layer_id}"
                                    
            arcpy.analysis.Clip(            
                in_features=layer_url,                                
                clip_features=buffer_path,                            
                out_feature_class=output_fc_path                    
            )
                                    
            arcpy.AddMessage(f"   --> SUCCESS! Clipping of {validated_name} is complete! Now, the DATE!")
                                    
            date_field_name = "Extract_date"          
            arcpy.management.AddField(                                
                in_table=output_fc_path,                                 
                field_name=date_field_name,            
                field_type="DATE",                                 
                field_alias="Extraction Date"                        
            )
            arcpy.AddMessage(f"""   --> Added '{date_field_name}' field. It will 
mark the day!""")
                                    
            arcpy.management.CalculateField(                                
                in_table=output_fc_path,                              
                field=date_field_name,                                
                expression="datetime.date.today()",                                
                expression_type="PYTHON3",                      
                code_block="import datetime"           
            )
            arcpy.AddMessage(f"   --> Populated '{date_field_name}' with TODAY's glorious date.")
            success_count += 1
        except arcpy.ExecuteError:
            error_message = arcpy.GetMessages(2)
            arcpy.AddError(f"""   --> FAILURE!
Layer {layer_raw_name} has RESISTED! ArcPy is WEAK! Error: {error_message}""")
        except Exception as e:
            arcpy.AddError(f"   --> FAILURE! Layer {layer_raw_name} encountered UNEXPECTED error! MUST BE SABOTAGE! Error: {e}")
                
    arcpy.AddMessage(f"\n--- Administrative Layer Population Complete: {success_count} layers secured for the Union! ---")
    return True

# --- HELPER FUNCTION: POPULATE CADASTRE LAYERS (RUSSIAN FLAVOUR) ---
def populate_cadastre_from_service(gdb_path, buffer_path, feature_service_url):        
    """   
    Clips all layers in the NSW Land Parcel Property Theme service to the site buffer,
    saves them to the 'Cadastre' feature dataset, and adds/populates an 'Extract_date' field.
    """
    arcpy.AddMessage("\n--- COMRADE! Begin GREAT WORK on Cadastre Data Extraction! Must stamp with DATE of VICTORY! ---")
            
    # 1. Get the Service JSON to find all layers
    try:
        response = requests.get(feature_service_url + '?f=json', timeout=15)
        response.raise_for_status()
        service_data = response.json()
    except requests.exceptions.RequestException as e:
        arcpy.AddError(f"""NYET! Feature Service URL: {feature_service_url} is FAILING ME! IT IS 
TREASON! Error: {e}""")          
        return False
                
    layers = service_data.get('layers', [])
            
    if not layers:
        arcpy.AddWarning("DA? Metadata says NYET layers! Service is EMPTY like Gulag ration. Warning.")
        return False

    cadastre_ds_path = os.path.join(gdb_path, 'Cadastre')
    if not arcpy.Exists(cadastre_ds_path):             
        arcpy.AddWarning(f"Cadastre Feature Dataset not found at: {cadastre_ds_path}. Skipping population. This is UNACCEPTABLE.")                
        return False
                    
    arcpy.AddMessage(f"""We have captured {len(layers)} layers for Motherland!
Prepare for geographic SUBTRACTION...""")
    success_count = 0
            
    # 2. Loop through each layer
    for layer in layers:
        layer_id = layer['id']
        layer_raw_name = layer['name']
                                
        # --- Use arcpy.ValidateTableName for robust naming ---        
        base_name = f"T{layer_id}_{layer_raw_name}"                      
        try:
            validated_name = arcpy.ValidateTableName(base_name, cadastre_ds_path)                 
        except Exception as name_e:
            arcpy.AddWarning(f"""   --> FAILED to validate name for 
layer {layer_raw_name}. Skipping. Error: {name_e}. Must work harder next time!""")
            continue
                                
        output_fc_path = os.path.join(cadastre_ds_path, validated_name)                  
        if arcpy.Exists(output_fc_path):                         
            arcpy.AddWarning(f" - Layer {layer_raw_name} already exists. Skipping. Efficiency is for the WEAK!")
            success_count += 1                         
            continue
                                
        arcpy.AddMessage(f""" - Processing Layer {layer_id}: {layer_raw_name} (Save to Geodatabase as: {validated_name}).
GO! GO! GO!""")
                        
        try:
            layer_url = f"{feature_service_url}/{layer_id}"
                                    
            arcpy.analysis.Clip(            
                in_features=layer_url,                                
                clip_features=buffer_path,                            
                out_feature_class=output_fc_path                    
            )
                                    
            arcpy.AddMessage(f"   --> SUCCESS! Clipping of {validated_name} is complete! Now, the DATE!")
                                    
            date_field_name = "Extract_date"          
            arcpy.management.AddField(                                
                in_table=output_fc_path,                                 
                field_name=date_field_name,            
                field_type="DATE",                                 
                field_alias="Extraction Date"                        
            )
            arcpy.AddMessage(f"""   --> Added '{date_field_name}' field. It will 
mark the day!""")
                                    
            arcpy.management.CalculateField(                                
                in_table=output_fc_path,                              
                field=date_field_name,                                
                expression="datetime.date.today()",                                
                expression_type="PYTHON3",                      
                code_block="import datetime"           
            )
            arcpy.AddMessage(f"   --> Populated '{date_field_name}' with TODAY's glorious date.")
            success_count += 1
        except arcpy.ExecuteError:
            error_message = arcpy.GetMessages(2)
            arcpy.AddError(f"""   --> FAILURE!
Layer {layer_raw_name} has RESISTED! ArcPy is WEAK! Error: {error_message}""")
        except Exception as e:
            arcpy.AddError(f"""   --> FAILURE! Layer {layer_raw_name} encountered UNEXPECTED error! MUST BE SABOTAGE! Error: {e}""")
                
    arcpy.AddMessage(f"\n--- Cadastre Layer Population Complete: {success_count} layers secured for the Union! ---")
    return True

# --- HELPER FUNCTION: POPULATE FLORA LAYERS (TARGETED EXTRACTION PROTOCOL) ---
def populate_flora_from_service(gdb_path, clip_features_path, project_number, map_service_url, subject_site_area_sqm):        
    """
    Connects to the specified MapServer, clips only Layer 3 (Plant Community Type) 
    against the subject site boundary, performs a dissolve, calculates area attributes,
    ADDS THE EXTRACT DATE, and saves the final feature class into the 'Flora' feature dataset.
    """
    arcpy.AddMessage("\n--- COMRADE! Begin BIOLOGICAL ANALYSIS! Extracting SECRET FLORA data from MapServer! ---")
            
    # 1. Get the Service JSON to find all layers
    try:
        response = requests.get(map_service_url + '?f=json', timeout=15)
        response.raise_for_status()
        service_data = response.json()
    except requests.exceptions.RequestException as e:
        arcpy.AddError(f"NYET! Flora MapServer URL: {map_service_url} is FAILING! The ECO-PLANS are COMPROMISED! Error: {e}")  
        return False
                
    layers = service_data.get('layers', [])
            
    if not layers:
        arcpy.AddWarning("DA? MapServer reports NYET layers! The data is hiding! Warning.")
        return False

    flora_ds_path = os.path.join(gdb_path, 'Flora')
    if not arcpy.Exists(flora_ds_path):
        arcpy.AddWarning(f"""Flora Feature Dataset not found at: {flora_ds_path}. 
Skipping Flora population. This is A TRAGEDY.""")
        return False
                    
    arcpy.AddMessage(f"""Found {len(layers)} layers of vegetation data.
Targeting only Layer 3 for surgical extraction, clipped against: {os.path.basename(clip_features_path)}.""")
    success_count = 0
    temp_clip_fc_path = None # Initialise variable outside of loop
        
    try:
        # Define temporary feature class for the result of the initial clip
        temp_clip_fc_name = f"Clipped_PCT_{project_number}_TEMP"
        temp_clip_fc_path = os.path.join(arcpy.env.scratchGDB, temp_clip_fc_name)
                         
        # Define final dissolved feature class name               
        new_fc_name = f"Plant_Community_Type_{project_number}"
        try:
            validated_name = arcpy.ValidateTableName(new_fc_name, flora_ds_path)                 
        except Exception as name_e:
            arcpy.AddWarning(f"   --> CRITICAL FAILURE: FAILED to validate final output name. Error: {name_e}.")  
            return False
                                    
        final_output_fc_path = os.path.join(flora_ds_path, validated_name)                 

        # Check if the feature class already exists (for re-running the tool)        
        if arcpy.Exists(final_output_fc_path):             
            arcpy.AddWarning(f""" - Final dissolved layer {new_fc_name} already exists.
Skipping. DUPLICATION is INEFFICIENT.""")
            return True # Success if it already exists

        # 2. Loop through each layer
        for layer in layers:
            layer_id = layer['id']
            layer_raw_name = layer['name']
                          
            # *** OPTIMISATION: Target only Layer 3 (Plant Community Type) *** if layer_id != 3:
            if layer_id != 3:
                arcpy.AddMessage(f" - Ignoring Layer {layer_id}: {layer_raw_name}. Only Layer 3 is required. EFFICIENCY!")
                continue
          
                                        
            arcpy.AddMessage(f" - Processing Flora Layer {layer_id}: {layer_raw_name}. INITIATE CLIP against Subject Site!")
                                    
            try:              
                layer_url_full = f"{map_service_url}/{layer_id}"
                                                                
                # --- STEP 1: CLIP (to a temporary location) ---                       
                arcpy.analysis.Clip(                                        
                    in_features=layer_url_full,                                        
                    clip_features=clip_features_path, # Subject Site Boundary Path        
                    out_feature_class=temp_clip_fc_path # Temporary Scratch GDB location                                
                )
                arcpy.AddMessage(f"""   --> CLIP SUCCESS!
Data secured in temporary location: {os.path.basename(temp_clip_fc_path)}.""")
                                                
                # --- STEP 2: DISSOLVE ---                
                # Fields requested by the user                
                dissolve_fields = ["PCTID", "PCTName", "vegForm", 
"vegClass", "form_PCT", "labels"]                              
                arcpy.AddMessage(f"   --> INITIATING DISSOLVE on fields: {', '.join(dissolve_fields)}.")
                                                
                arcpy.management.Dissolve(           
                    in_features=temp_clip_fc_path,                                         
                    out_feature_class=final_output_fc_path, # Final location in Flora GDB                    
                    dissolve_field=dissolve_fields,    
                    multi_part="MULTI_PART" # Multi-polygon enabled                                
                )
                arcpy.AddMessage(f"   --> DISSOLVE SUCCESS! Final layer created at: {final_output_fc_path}.")  
                                                       
                # --- STEP 3: CALCULATE ATTRIBUTES ---                
                arcpy.AddMessage("   --> CALCULATING ATTRIBUTES: Area (Hectares), Area (square metres), and Area (% of Subject Site Area).")       
                                          
                # 3a. Add fields                
                area_ha_field = "Area_ha"                
                area_sqm_field = "Area_sqm"                
                area_pct_field = "Area_Pct"                                             
                arcpy.management.AddField(final_output_fc_path, area_ha_field, "DOUBLE", field_alias="Area (Hectares)")                
                arcpy.management.AddField(final_output_fc_path, area_sqm_field, "DOUBLE", field_alias="Area (Square Metres)")                
                arcpy.management.AddField(final_output_fc_path, area_pct_field, "DOUBLE", field_alias="Area (% of Subject Site)")                                                 
                                
                # 3b. Calculate Area Fields                
                arcpy.management.CalculateField(                                        
                    in_table=final_output_fc_path,                                        
                    field=area_sqm_field,  
                    expression="!shape.area@squaremeters!",                                        
                    expression_type="PYTHON3"                  
                )    
                arcpy.AddMessage("   --> Calculated Area (square metres).")                                                                
                arcpy.management.CalculateField(                 
                    in_table=final_output_fc_path,                               
                    field=area_ha_field,                                        
                    expression="!shape.area@hectares!",      
                    expression_type="PYTHON3"                                
                )
                arcpy.AddMessage("   --> Calculated Area (Hectares).")            
                                  
                # 3c. Calculate Percentage Area Field                
                if subject_site_area_sqm and subject_site_area_sqm > 0:
                    code_block = f"def calculate_pct(feature_area_sqm):\n    total_site_area = {subject_site_area_sqm}\n    if total_site_area > 0 and feature_area_sqm is not None:\n        return (feature_area_sqm / total_site_area) * 100\n    return 0"                 
                    arcpy.management.CalculateField(                                                
                        in_table=final_output_fc_path,                             
                        field=area_pct_field,                                                
                        expression=f"calculate_pct(!{area_sqm_field}!)",                                 
                        expression_type="PYTHON3",                                                
                        code_block=code_block                                        
                    ) 
                    arcpy.AddMessage("   --> Calculated Area (% of Subject Site Area).")
                else:                          
                    arcpy.AddWarning("""   --> WARNING: Subject Site Area is zero or unknown.
Skipping percentage calculation.""")
                                                
                # --- STEP 4: ADD AND POPULATE EXTRACT DATE ---                
                date_field_name = "Extract_date"                       
                arcpy.management.AddField(                                        
                    in_table=final_output_fc_path,                                         
                    field_name=date_field_name,              
                    field_type="DATE",                                      
                    field_alias="Extraction Date"                                
                )  
                arcpy.AddMessage(f"   --> Added '{date_field_name}' field. It will mark the day!")                                                
                arcpy.management.CalculateField(                           
                    in_table=final_output_fc_path,                                        
                    field=date_field_name,                                        
                    expression="datetime.date.today()",       
                    expression_type="PYTHON3",                                        
                    code_block="import datetime"                                
                )          
                arcpy.AddMessage(f"   --> Populated '{date_field_name}' with TODAY's glorious date.")                                      
                arcpy.AddMessage(f"""   --> FINAL SUCCESS!
Targeted Flora data processing complete.""")
                success_count += 1
                break # Exit the loop after processing Layer 3
            
            except arcpy.ExecuteError:
                error_message = arcpy.GetMessages(2)                       
                arcpy.AddWarning(f"""   --> FAILED to process Flora layer {layer_raw_name}. ArcPy Error: {error_message}. THE SYSTEM RESISTED!""")
            except Exception as e:
                arcpy.AddWarning(f"   --> FAILED to process Flora layer {layer_raw_name}. UNFORESEEN ERROR: {e}. Report to HQ.")

    finally:
        # Final cleanup of the temporary clip feature class        
        if arcpy.Exists(temp_clip_fc_path):          
            arcpy.AddMessage(f"   --> Cleaning up temporary file: {os.path.basename(temp_clip_fc_path)}. WIPE THE SLATE CLEAN!")
            arcpy.management.Delete(temp_clip_fc_path)
                                
    arcpy.AddMessage(f"""\n--- Flora Data Extraction Complete: {success_count} layers of vital biological intelligence secured.
---""")
    return True

# --- HELPER FUNCTION: POPULATE PLANNING LAYERS (LZN) ---
def populate_planning_layers_from_service(gdb_path, buffer_path, map_service_url, layer_id, layer_name):        
    """
    Connects to the specified MapServer, clips a single layer (e.g., LZN) to the site buffer,
    saves it to the 'Planning' feature dataset, and adds an 'Extract_date' field.
    """
    arcpy.AddMessage("\n--- COMRADE! Begin PLANNING ANALYSIS! Extracting SECRET ZONING data from MapServer! ---")
            
    planning_ds_path = os.path.join(gdb_path, 'Planning')
    if not arcpy.Exists(planning_ds_path):
        arcpy.AddError(f"Planning Feature Dataset not found at: {planning_ds_path}. Extraction ABORTED!")
        return False

    # Requested output name is LZN
    final_fc_name = layer_name         
    output_fc_path = os.path.join(planning_ds_path, arcpy.ValidateTableName(final_fc_name, planning_ds_path))           
    if arcpy.Exists(output_fc_path):
        arcpy.AddWarning(f" - Layer {final_fc_name} already exists. Skipping. DUPLICATION is INEFFICIENT.")
        return True

    arcpy.AddMessage(f" - Processing Planning Layer {layer_id} ({final_fc_name}). INITIATE CLIP against Buffer!")
            
    try:
        layer_url_full = f"{map_service_url}/{layer_id}"
                                
        # --- STEP 1: CLIP against the 2000m Buffer ---        
        arcpy.analysis.Clip(                        
            in_features=layer_url_full,                   
            clip_features=buffer_path, # Clip against the 2000m Buffer feature class            
            out_feature_class=output_fc_path                
        )
        arcpy.AddMessage(f"   --> CLIP SUCCESS! Data secured for {final_fc_name}.")
                        
        # --- STEP 2: ADD AND POPULATE EXTRACT DATE ---        
        date_field_name = "Extract_date"                        
        arcpy.management.AddField(                        
            in_table=output_fc_path,                         
            field_name=date_field_name,                         
            field_type="DATE",                    
            field_alias="Extraction Date"                
        )
        arcpy.AddMessage(f"""   --> Added 
'{date_field_name}' field. It will mark the day!""")
                        
        # Use Python's datetime for the calculation        
        arcpy.management.CalculateField(                        
            in_table=output_fc_path,                        
            field=date_field_name,        
            expression="datetime.date.today()",             
            expression_type="PYTHON3",                        
            code_block="import datetime"                
        )
        arcpy.AddMessage(f"   --> Populated '{date_field_name}' with TODAY's glorious date.")
        arcpy.AddMessage(f"""\n--- Planning Data Extraction Complete: 
1 layer of crucial zoning intelligence secured. ---""")
                
        return True
    except arcpy.ExecuteError:
        error_message = arcpy.GetMessages(2)               
        arcpy.AddError(f"   --> FAILURE! Layer {layer_name} has RESISTED! ArcPy is WEAK! Error: {error_message}")
        return False
    except Exception as e:
        arcpy.AddError(f"""   --> FAILURE! Layer {layer_name} encountered UNEXPECTED 
error! MUST BE SABOTAGE! Error: {e}""")
        return False

# --- NEW HELPER FUNCTION: POPULATE BUSHFIRE LAYERS ---
def populate_bushfire_layer_from_service(gdb_path, buffer_path, feature_service_url):
    """
    Clips the Bush Fire Prone Land layer to the site buffer,
    saves it to the 'Bushfire' feature dataset, and adds an 'Extract_date' field.
    """
    layer_name = "Bushfire_Prone_Land"
    arcpy.AddMessage(f"\n--- COMRADE! Begin FIRE ANALYSIS! Extracting {layer_name} data! ---")
    
    bushfire_ds_path = os.path.join(gdb_path, 'Bushfire')
    if not arcpy.Exists(bushfire_ds_path):
        arcpy.AddError(f"Bushfire Feature Dataset not found at: {bushfire_ds_path}. Extraction ABORTED!")
        return False
            
    final_fc_name = layer_name
    output_fc_path = os.path.join(bushfire_ds_path, arcpy.ValidateTableName(final_fc_name, bushfire_ds_path))
        
    if arcpy.Exists(output_fc_path):
        arcpy.AddWarning(f""" - Layer {final_fc_name} already 
exists. Skipping. DUPLICATION is INEFFICIENT.""")
        return True
        
    arcpy.AddMessage(f" - Processing Bushfire Layer: {final_fc_name}. INITIATE CLIP against Buffer!")
        
    try:
        # --- STEP 1: CLIP against the 2000m Buffer ---        
        arcpy.analysis.Clip(
            in_features=feature_service_url, # Layer 0 is the required layer
            # FIX: Removed the line break that caused the SyntaxError
            clip_features=buffer_path, # Clip against the 2000m Buffer feature class
            out_feature_class=output_fc_path
        )
        arcpy.AddMessage(f"""   --> CLIP SUCCESS!
Data secured for {final_fc_name}.""")
                
        # --- STEP 2: ADD AND POPULATE EXTRACT DATE ---        
        date_field_name = "Extract_date"                
        arcpy.management.AddField(
            in_table=output_fc_path,             
            field_name=date_field_name,             
            field_type="DATE",        
            field_alias="Extraction Date"        
        )
        arcpy.AddMessage(f"   --> Added '{date_field_name}' field. It will mark the day!")
                
        # Use Python's datetime for the calculation        
        arcpy.management.CalculateField(
            in_table=output_fc_path,
            field=date_field_name,
            expression="datetime.date.today()",  
            expression_type="PYTHON3",
            code_block="import datetime"
        )
        arcpy.AddMessage(f"   --> Populated '{date_field_name}' with TODAY's glorious date.")
        arcpy.AddMessage(f"\n--- Bushfire Data Extraction Complete: 1 layer of crucial fire intelligence secured. ---")
        return True

    except arcpy.ExecuteError:
        error_message = arcpy.GetMessages(2)        
        arcpy.AddError(f"""   --> FAILURE! Layer {layer_name} has RESISTED! ArcPy is WEAK!
Error: {error_message}""")
        return False
    except Exception as e:
        arcpy.AddError(f"   --> FAILURE! Layer {layer_name} encountered UNEXPECTED error! MUST BE SABOTAGE! Error: {e}")
        return False

# --- HELPER FUNCTION FOR PROJECT CREATION ---
def create_pro_project(project_number, project_description, template_path, source_fc_path, overwrite_project, weeds_fc_path=None):        
    """
    Creates a new ArcGIS Pro project structure, copies site feature, adds buffer,
    calculates fields, and copies the optional WAPWeeds layer.
    Returns: (full_new_gdb_path, buffer_output_path, full_new_aprx_path) or (None, None, None)
    """        
    # Define the base location for all projects
    project_base_dir = r"C:\ArcGIS Projects"
        
    # Define the new project name and full path
    project_name = f"AEP{project_number}"
    project_path = os.path.join(project_base_dir, project_name)

    arcpy.AddMessage(f"\n--- Initiating Project Site Workspace Creation for: {project_name}. BUILD THE STRUCTURE! ---")

    # Initialize return values    
    full_new_aprx_path = None  
    full_new_gdb_path = None    
    buffer_output_path = None
    
    # NEW VARIABLES FOR WEEDS LAYER
    weeds_copied = False
    target_weeds_path = None
    validated_weeds_name = None
        
    try:
        # Check if the base directory exists        
        if not os.path.isdir(project_base_dir):
            arcpy.AddError(f"Error: Base directory does not exist: {project_base_dir}. This is IMPOSSIBLE!")
            return None, None, None
         
        # MANDATORY TEMPLATE CHECK        
        if not template_path or not os.path.isdir(template_path): 
            arcpy.AddError(f"""Error: Template folder not found at provided path: {template_path}.
The TEMPLATE has VANISHED!""")
            return None, None, None
         
        # Template Copy/Deletion Logic        
        if os.path.exists(project_path):
            if overwrite_project:
                arcpy.AddMessage(f"PROJECT FOLDER EXISTS at {project_path}! Overwrite selected. INITIATING DESTRUCTION PROTOCOL RMTREE!")
                try:      
                    shutil.rmtree(project_path)
                    arcpy.AddMessage(f"DESTRUCTION COMPLETE! Project folder is annihilated. Ready for new construction!")
                except Exception as e:
                    arcpy.AddError(f"CRITICAL FAILURE! Cannot delete existing project folder: {e}. Project creation ABORTED!")  
                    return None, None, None
            else:
                arcpy.AddWarning(
                    f"""Project folder {project_path} 
already exists. Overwrite not selected. PROJECT CREATION ABORTED! 
Set 'Overwrite Existing Project Folder' to TRUE to proceed with deletion.
You must choose, COMRADE!"""
                )
                return None, None, None

        shutil.copytree(template_path, project_path)
        arcpy.AddMessage(f"Successfully copied template to: {project_path}. GLORY to the efficiency!")                            

        # Renaming Logic        
        new_aprx_name = f"AEP{project_number}_{project_description}.aprx"
        new_gdb_name = f"AEP{project_number}.gdb"
        aprx_renamed = False
        gdb_renamed = False
                
        for item_name in os.listdir(project_path):
            full_old_path = os.path.join(project_path, item_name)                     

            # RENAME APRX FILE 
            if item_name.lower().endswith(".aprx") and not aprx_renamed:
                full_new_path = os.path.join(project_path, new_aprx_name)
                if not os.path.exists(full_new_path):
                    os.rename(full_old_path, full_new_path)                           
                    aprx_renamed = True
                    full_new_aprx_path = full_new_path

            # RENAME GDB FOLDER            
            elif item_name.lower().endswith(".gdb") and os.path.isdir(full_old_path) and not gdb_renamed:
                full_new_path = os.path.join(project_path, new_gdb_name)                       
                if not os.path.exists(full_new_path):
                    os.rename(full_old_path, full_new_path)
                    gdb_renamed = True
                    full_new_gdb_path = full_new_path
                            
            if aprx_renamed and gdb_renamed:                  
                break

        # Default GDB and Map Setting Logic        
        if aprx_renamed and gdb_renamed and full_new_aprx_path and full_new_gdb_path:
            arcpy.AddMessage("""Updating Project's Default Geodatabase and Adding Site Feature.
MAKE IT OFFICIAL!""")
            try:
                p = arcpy.mp.ArcGISProject(full_new_aprx_path)
                p.defaultGeodatabase = full_new_gdb_path                                                

                # --- *** Create standard Feature Datasets *** ---                          
                arcpy.AddMessage("""Creating standard project feature datasets. INITIATE PROTOCOL ALPHA!""")                                                

                # GDA2020 / NSW Lambert (EPSG: 9473)       
                sr = arcpy.SpatialReference(9473)                                                               
                datasets_to_create = [                   
                    'AdminBoundaries',     
                    'Cadastre',                                      
                    'Flora',                             
                    'Fauna',                                      
                    'Arborculture',                     
                    'Aquatic',                                
                    'SiteFeatures',                                      
                    'Planning', # Added Planning Feature Dataset                   
                    'Bushfire' # Added Bushfire Feature Dataset                
                ]           
                                                   
                for ds_name in datasets_to_create:
                    try:
                        ds_path = os.path.join(full_new_gdb_path, 
ds_name)
                        if not arcpy.Exists(ds_path):
                            arcpy.management.CreateFeatureDataset(                                
                                out_dataset_path=full_new_gdb_path,          
                                out_name=ds_name,                                            
                                spatial_reference=sr                            
                            )      
                            arcpy.AddMessage(f""" - Created Dataset: {ds_name}.
More storage for the Motherland!""")
                        else:
                            arcpy.AddWarning(f" - Dataset '{ds_name}' already exists. Skipping. Waste not, want not.")
                    except Exception as ds_e:           
                        arcpy.AddWarning(f" - Could not create dataset '{ds_name}'. Error: {ds_e}. We will deal with this LATER.")

                # --- *** END of Dataset Creation *** ---                                      
                                      
                # Copy the source feature class to the new default GDB                       
                target_fc_name = os.path.basename(source_fc_path)
                target_fc_path = os.path.join(full_new_gdb_path, 'SiteFeatures', target_fc_name)
                arcpy.AddMessage(f"Copying {target_fc_name} to the 'SiteFeatures' dataset. ENSURE DATA FIDELITY!")           
                arcpy.management.CopyFeatures(source_fc_path, target_fc_path)
                arcpy.AddMessage("Copy complete. Data secured.")                                                

                # --- *** NEW: Copy Optional WAPWeeds Layer to SiteFeatures *** ---
                if weeds_fc_path and arcpy.Exists(weeds_fc_path):
                    weeds_fc_name_raw = os.path.basename(weeds_fc_path)
                    validated_weeds_name = arcpy.ValidateTableName(weeds_fc_name_raw, full_new_gdb_path)
                    target_weeds_path = os.path.join(full_new_gdb_path, 'SiteFeatures', validated_weeds_name)

                    arcpy.AddMessage(f"Copying optional layer: {weeds_fc_name_raw} to 'SiteFeatures' as {validated_weeds_name}. MUST SECURE THE BIOLOGICAL THREATS!")
                    try:
                        arcpy.management.CopyFeatures(weeds_fc_path, target_weeds_path)
                        arcpy.AddMessage("Weeds layer copy complete. The enemy is catalogued.")
                        weeds_copied = True
                    except Exception as copy_e:
                        arcpy.AddWarning(f"WARNING: Failed to copy Weeds layer from {weeds_fc_path}. Error: {copy_e}. The THREAT ESCAPED!")
                elif weeds_fc_path:
                    arcpy.AddWarning(f"WARNING: Optional Weeds Feature Class path provided ({weeds_fc_path}) but it does not exist. Skipping.")
                # --- *** END OF NEW WEEDS LOGIC *** ---


                # Add Project Details Fields                
                project_no_field_safe = "Project_No"     
                arcpy.management.AddField(target_fc_path, project_no_field_safe, "TEXT", field_length=7, field_alias="Project Number")
                arcpy.management.CalculateField(in_table=target_fc_path, field=project_no_field_safe, expression=f"'{project_number}'", expression_type="PYTHON3")                                                              
                
                project_desc_field_safe = "Project_Desc" 
                arcpy.management.AddField(target_fc_path, project_desc_field_safe, "TEXT", field_length=100, field_alias="Project Description")
                arcpy.management.CalculateField(in_table=target_fc_path, field=project_desc_field_safe, expression=f"'{project_description}'", expression_type="PYTHON3")                                                
                
                # Area and Large Site Calculation        
                area_field_name_safe = "Area_ha"
                arcpy.management.AddField(target_fc_path, area_field_name_safe, "DOUBLE", field_alias="Area ha")
                arcpy.management.CalculateField(in_table=target_fc_path, field=area_field_name_safe, expression="!shape.area@hectares!", expression_type="PYTHON3", field_type="DOUBLE")                                                  
                                
                large_site_field_name_safe = "Large_Site" 
                arcpy.management.AddField(target_fc_path, large_site_field_name_safe, "TEXT", field_length=3, field_alias="Large Site")
                                # FIX for SyntaxError: Using a clean, single-line expression for robustness                
                code_block = "def is_large(area): return 'Yes' if area is not None and area >= 50 else 'No'"
                arcpy.management.CalculateField(                    
                    in_table=target_fc_path,                     
                    field=large_site_field_name_safe,           
                    expression=f"is_large(!{area_field_name_safe}!)",                     
                    expression_type="PYTHON3",                     
                    code_block=code_block                
                )                                
                                
                # Create 2000m Buffer of the Target Site                
                buffer_distance = "2000 Meters"
                buffer_fc_name = "TargetSite_Buffer_2000m"
                buffer_output_path = os.path.join(full_new_gdb_path, 'SiteFeatures', buffer_fc_name)
                
                buffer_created = False
                arcpy.AddMessage(f"""Creating {buffer_distance} protective buffer.
WE BUILD THE WALL!""")
                                
                try:
                    arcpy.analysis.Buffer(                                             
                        in_features=target_fc_path,                                                 
                        out_feature_class=buffer_output_path,                                    
                        buffer_distance_or_field=buffer_distance,            
                        dissolve_option="ALL"                                        
                    )
                    arcpy.AddMessage(f"""Successfully created buffer: 
{buffer_fc_name}. THE WALL IS STRONG!""")
                    buffer_created = True
                except Exception as buffer_e:
                    arcpy.AddWarning(f"WARNING: Could not create {buffer_distance} buffer. Error: {buffer_e}. The wall is WEAK!")         
                    buffer_output_path = None
                                                                     
                # Add the copied feature class (and buffer/weeds) to the Map        
                map_name = "Map 1 - Site Details" 
                target_map = None
                                
                for map_item in p.listMaps():                                
                    if map_item.name == map_name:
                        target_map = map_item
                        break
                                             
                if target_map:
                    target_map.addDataFromPath(target_fc_path)
                    
                    if buffer_created and buffer_output_path:
                        try:     
                            target_map.addDataFromPath(buffer_output_path)                             
                        except Exception as add_buffer_e:
                            # FIX APPLIED HERE (previous fix for line 744)
                            arcpy.AddWarning(f"""WARNING: Could not add buffer layer to map.
Error: {add_buffer_e}.""")
                    
                    # --- *** NEW: Add Weeds Layer to Map *** ---
                    if weeds_copied and target_weeds_path:
                        try:
                            target_map.addDataFromPath(target_weeds_path)
                            arcpy.AddMessage(f"Weeds layer {validated_weeds_name} added to Map.")
                        except Exception as add_weeds_e:
                            arcpy.AddWarning(f"WARNING: Could not add weeds layer to map. Error: {add_weeds_e}.")
                    # --- *** END OF NEW WEEDS MAP LOGIC *** ---

                    try:
                        extent = arcpy.Describe(target_fc_path).extent     
                        cam = target_map.defaultCamera
                        cam.setExtent(extent)
                        target_map.defaultCamera = cam
                        arcpy.AddMessage("""Telescope is adjusted! Map now 
views the Subject Site like Eagle of the Steppe.""")
                    except Exception as zoom_e:
                        arcpy.AddWarning(f"WARNING: Could not zoom map camera to the site feature extent. Error: {zoom_e}. Magnification failed!")
                   
                p.save()                           
                arcpy.AddMessage(f"Saved changes to project file: {os.path.basename(full_new_aprx_path)}. THE RECORD IS SECURE.")
                                                
                return full_new_gdb_path, buffer_output_path, full_new_aprx_path                                         

            except Exception as mp_e:
                arcpy.AddWarning(f"""WARNING: Could not update the ArcGIS Pro project's default GDB or add site feature.
Error: {mp_e}. The project is UNSTABLE!""")
                # Re-raise the exception to show the full stack trace for debugging if required.                
                raise # Critical error in project setup must be reported.
        else:                         
            arcpy.AddWarning("""WARNING: APRX or GDB was not renamed successfully, 
skipping default GDB assignment. SABOTAGE!""")
            return None, None, None
            
    except Exception as e:
        arcpy.AddError(f"Failed to set up the project workspace: {e}. The entire FRAMEWORK is SHATTERED!")
        return None, None, None

# --- TOOLBOX CLASS (UNCHANGED) ---
class Toolbox(object):
    def __init__(self):
        self.label = "Spatial Data Tools"
        self.alias = "SDT"
        # FIX APPLIED HERE: The list must follow the assignment operator on the same line,
        # or use parentheses/backslashes for continuation.
        self.tools = [CreateProjectFramework]

# --- UNIFIED TOOL: CREATE PROJECT FRAMEWORK ---
class CreateProjectFramework(object):
    def __init__(self):
        self.label = "Create Project Framework"
        self.description = "Queries the NSW parcels, creates a consolidated site feature, and sets up the ArcGIS Pro project workspace using a template."
        self.canRunInBackground = False
        
    def getParameterInfo(self):
        param0 = arcpy.Parameter(                     
            displayName="Lot/Plan ID List ([lot]//DP[Plan Number]) (Comma-Separated)",
            name="lot_plan_input",
            datatype="GPString",
            direction="Input",
            parameterType="Required",
            symbology="1//DP90465, 3//DP171105"                 
        )
        param0.value = "1//DP90465,3//DP171105,4//DP171105,1//DP1133689"     
    
        param1 = arcpy.Parameter(                
            displayName="Output Target Site Feature Class",
            name="output_fc",
            datatype="DEFeatureClass", 
            direction="Output",
            parameterType="Required"
        )                  
                      
        param2 = arcpy.Parameter(                        
            displayName="Project Number (7 characters max)",
            name="project_number_input",
            datatype="GPString",
            direction="Input",
            parameterType="Required",        
            symbology="AEP-0001"
        )
        param2.value = "6666"
        
        param3 = arcpy.Parameter(                     
            displayName="Project Description (100 characters max)",
            name="project_description_input",
            datatype="GPString",
            direction="Input",       
            parameterType="Required",
            symbology="Brief description of project purpose."
        )
        param3.value = "Devils Pinch"                                         
        
        param4 = arcpy.Parameter(                 
            displayName="Template Project Folder Path (REQUIRED)",
            name="template_path_input",
            datatype="DEFolder", 
            direction="Input",
            parameterType="Required",
            symbology=r"C:\ArcGIS Templates\AEP_STD_Template"                 
        )          
          
        # *** NEW PARAMETER FOR WEEDS FC (INDEX 5) ***
        param5 = arcpy.Parameter(
            displayName="Optional Weeds Feature Class (WAPWeeds...)",
            name="weeds_fc_input",
            datatype="DEFeatureClass", 
            direction="Input",
            parameterType="Optional",
            symbology=r"C:\Data\WAPWeeds.gdb\WAPWeeds_2025_Site"
        )
          
        # OVERWRITE PROJECT (SHIFTED TO INDEX 6)
        param6 = arcpy.Parameter(                        
            displayName="Overwrite Existing Project Folder (DESTRUCTION PROTOCOL)",
            name="overwrite_project",
            datatype="GPBoolean", 
            direction="Input",
            parameterType="Optional"
        ) 
        param6.value = False                                 
        
        return [param0, param1, param2, param3, param4, param5, param6]

    def updateParameters(self, parameters):
        param_project_number = parameters[2]
        param_output_fc = parameters[1]
                
        if param_project_number.value:         
            project_number = param_project_number.valueAsText
            default_name = f"Subject_Site_{project_number}"
                      
            if not param_output_fc.altered:
                param_output_fc.value = default_name
                return
                
    def execute(self, parameters, messages):
        """Contains the core logic."""     
                                    
        # Initialize variables needed for the finally block        
        success = False                 
        project_success = False
        aprx_path = None                         

        # We must retrieve parameters here        
        lot_plan_list_str = parameters[0].valueAsText
        output_fc = parameters[1].valueAsText
        project_number = parameters[2].valueAsText
        project_description = parameters[3].valueAsText
        template_path = parameters[4].valueAsText
        weeds_fc_path = parameters[5].valueAsText # NEW PARAMETER INDEX 5
        overwrite_project = parameters[6].value # SHIFTED TO INDEX 6
        
        workspace = arcpy.env.scratchGDB            
        temp_json_file = os.path.join(arcpy.env.scratchFolder, "temp_results.json")
        temp_fc = os.path.join(workspace, 
"TempParcels")
        temp_dissolve_fc = os.path.join(workspace, "DissolvedParcels")

        try:
            # --- 1-7. Lot/Plan Query and Site Boundary Creation (unchanged) ---
            arcpy.AddMessage("Starting Lot/Plan query process... FETCH THE GEOMETRY!")
            # Input Validation and Query Construction
            if not lot_plan_list_str:
                arcpy.AddError("The Lot/Plan ID list cannot be empty. This is UNPROFESSIONAL!")
                return   
                            
            lot_ids_cleaned = []
            for lot_id in lot_plan_list_str.split(','):
                cleaned_id = lot_id.strip().upper()
                lot_ids_cleaned.append(f"'{cleaned_id}'")                         
                                
            where_clause = f"lotidstring IN ({','.join(lot_ids_cleaned)})"                                

            # Execute REST API Query            
            query_params = {
                'where': where_clause,              
                'outFields': '*',
                'returnGeometry': 'true',
                'f': 'json',
            }
            query_url = FEATURE_PARCEL_LAYER_URL + "/query"                    
                                
            try:
                response = requests.get(query_url, params=query_params, timeout=30)
                response.raise_for_status()                      
            except requests.exceptions.RequestException as e:           
                arcpy.AddError(f"""Connection has gone COLD! It is SIBERIA!
Error: {e}""")
                return             

            data = response.json()
            if 'error' in data:
                arcpy.AddError(f"FeatureServer Error: {data['error']['message']}. THEY HAVE BLOCKED US!")
                return               
                          
            if not data.get('features'):
                arcpy.AddWarning("Query returned zero features. No target parcels were found. Zero success is BAD!")
                parameters[1].value = None
                return                           
                          
            with open(temp_json_file, 'w') as f:                        
                json.dump(data, f)
            
            # Convert JSON to Temporary Feature Class            
            arcpy.conversion.JSONToFeatures(temp_json_file, temp_fc)
            if int(arcpy.management.GetCount(temp_fc).getOutput(0)) == 0:                
                arcpy.AddWarning("The JSON-to-Features conversion resulted in zero features. NYET! It is failure.")                       
                parameters[1].value = None
                return
            
            # Repair Geometry            
            arcpy.management.RepairGeometry(temp_fc)                       
                          
            # Dissolve the temporary parcels            
            arcpy.management.Dissolve(                       
                in_features=temp_fc,                                 
                out_feature_class=temp_dissolve_fc,               
                dissolve_field=None,                                 
                multi_part="MULTI_PART",                                 
                unsplit_lines="DISSOLVE_LINES"                
            )                                       
            
            # Simplify the boundary to create the final output            
            arcpy.management.CopyFeatures(temp_dissolve_fc, output_fc)
            arcpy.AddMessage(f"""Final site feature class created at: {output_fc}.
VICTORY!""")
            success = True
            
        except arcpy.ExecuteError:
            arcpy.AddError(f"""ArcPy tool is BROKEN! Error from tool: {arcpy.GetMessages(2)}""")
            success = False
        except Exception as e:
            arcpy.AddError(f"""A critical Python error occurred during script execution: {e}. I SENSE SABOTAGE! 💥""")         
            success = False
            
        finally:
            # --- 7. CLEANUP TEMPORARY FILES ---            
            arcpy.AddMessage("\nCleaning up temporary files. WIPE THE SLATE CLEAN, COMRADE!")                                    
            
            if arcpy.Exists(temp_fc):                
                arcpy.management.Delete(temp_fc)
            if arcpy.Exists(temp_dissolve_fc):                
                arcpy.management.Delete(temp_dissolve_fc)
            if os.path.exists(temp_json_file):                
                os.remove(temp_json_file)
                
            # --- 8. AUTOMATICALLY RUN PROJECT CREATION (Framework Setup) ---     
            if success:                                                
                try:
                    # Capture the new return values: GDB path, Buffer FC path, and APRX path           
                    # PASSED NEW ARGUMENT: weeds_fc_path
                    new_gdb_path, buffer_fc_path, aprx_path = create_pro_project(project_number, project_description, template_path, output_fc, overwrite_project, weeds_fc_path)
                except Exception as proj_e:                        
                    # Catch the re-raised exception from create_pro_project for the error message
                    arcpy.AddError(f"CRITICAL PROJECT SETUP FAILURE: {proj_e}")      
                    new_gdb_path, buffer_fc_path, aprx_path = None, None, None

                if new_gdb_path and buffer_fc_path and aprx_path:                       
                    project_success = True                  
                                            
                    # --- Determine Subject Site Boundary Path ---                    
                    site_fc_name = f"Subject_Site_{project_number}"                             
                    site_boundary_path = os.path.join(new_gdb_path, 'SiteFeatures', site_fc_name)                                                            

                    # --- Calculate Total Subject Site Area (in Square Metres) ---                    
                    subject_site_area_sqm = 0 
                                    
                    try:
                        with arcpy.da.SearchCursor(site_boundary_path, "SHAPE@AREA") as cursor:
                            for row in cursor:      
                                subject_site_area_sqm += row[0]
                    except Exception as area_e:
                        arcpy.AddWarning(f"""WARNING: Failed to calculate Subject Site Area (sqm).
Error: {area_e}""")
                        subject_site_area_sqm = 0
                                            
                    # --- 8.4. *** NEW: AUTOMATICALLY POPULATE ADMINISTRATIVE LAYERS *** ---                   
                    populate_success_admin = populate_admin_boundaries_from_service(new_gdb_path, buffer_fc_path, ADMIN_BOUNDARIES_SERVICE_URL)
                    if not populate_success_admin:
                        arcpy.AddWarning("""WARNING: Administrative boundary population encountered errors. THE BORDERS ARE IN DISPUTE!""")
                                       
                    # --- 8.5. AUTOMATICALLY POPULATE CADASTRE LAYERS ---                    
                    populate_success_cadastre = populate_cadastre_from_service(new_gdb_path, buffer_fc_path, FEATURE_SERVICE_URL)                      
                    if not populate_success_cadastre:                        
                        arcpy.AddWarning("""WARNING: Cadastre layer population encountered errors. DATA is IMPERFECT!""")
                        
                    # --- 8.6. AUTOMATICALLY POPULATE FLORA LAYERS (Targeted Site Clipping & Dissolve) ---                                    
                    populate_success_flora = populate_flora_from_service(new_gdb_path, site_boundary_path, project_number, FLORA_MAP_SERVICE_URL, subject_site_area_sqm)                  
                    if not populate_success_flora:
                        arcpy.AddWarning("""WARNING: Flora layer population encountered errors.
THE FLORA IS MYSTERIOUS!""")
                                                                                               
                    # --- 8.7. AUTOMATICALLY POPULATE PLANNING LAYERS (Buffer Clipping) ---                    
                    planning_layer_id = 11
                    planning_layer_name = "LZN" # Local Zoning Notification                                             
                    populate_success_planning = populate_planning_layers_from_service(                        
                        new_gdb_path,                         
                        buffer_fc_path, # Clip against the 2000m buffer                        
                        PLANNING_MAP_SERVICE_URL,           
                        planning_layer_id,
                        planning_layer_name                    
                    )
                    if not populate_success_planning:         
                        arcpy.AddWarning("""WARNING: Planning layer population encountered errors. THE ZONING IS UNKNOWN!""")
                                            
                    # --- 8.8. AUTOMATICALLY POPULATE BUSHFIRE LAYERS (Buffer Clipping) --- 
                    populate_success_bushfire = populate_bushfire_layer_from_service(new_gdb_path, buffer_fc_path, BUSHFIRE_PRONE_LAND_URL)
                    if not populate_success_bushfire:
                        arcpy.AddWarning("""WARNING: Bushfire layer population encountered errors.
THE FIRE RISK IS UNKNOWN!""")
                                                        
                else:
                    project_success = False

            # --- 9. FINAL CLEANUP: Delete 
            # the original output feature class if project setup was successful ---
            if project_success and arcpy.Exists(output_fc):
                arcpy.AddMessage(f"Removing redundant intermediate output feature class: {output_fc}. NO EVIDENCE!")
                try:
                    parameters[1].value = None             
                    arcpy.management.Delete(output_fc)
                    arcpy.AddMessage("Intermediate output successfully removed. The file is GONE!")
                except Exception as cleanup_e:
                    arcpy.AddWarning(f"WARNING: Could not delete the intermediate output FC at {output_fc}. Manual cleanup is required. DO YOUR JOB!") 

            # --- 10. FINAL STEP: Open Project in ArcGIS Pro (MOVED TO THE END) ---
            if project_success and aprx_path:
                try:
                    pro_exe_path = r"C:\Program Files\ArcGIS\Pro\bin\ArcGISPro.exe"                     
                            
                    if os.path.exists(pro_exe_path):
                        arcpy.AddMessage(f"""\n--- OPENING THE GREAT PRO PROJECT!
VIEW THE GLORY! ---""")
                        arcpy.AddMessage(f"Opening ArcGIS Pro project: {aprx_path}")
                        subprocess.Popen([pro_exe_path, aprx_path])
                        arcpy.AddMessage("ArcGIS Pro started in a new process. FOR SCIENCE!")
            
                    else:
                        arcpy.AddWarning(f"WARNING: ArcGIS Pro executable not found at expected path: {pro_exe_path}. Cannot open project automatically. NYET, THE EXECUTIONER IS MISSING!")
                except Exception as open_e:
                    arcpy.AddWarning(f"""WARNING: Failed to start ArcGIS Pro. Error: {open_e}. I require more 
POWER!""")
                                        
                return