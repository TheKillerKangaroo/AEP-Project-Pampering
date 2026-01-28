import arcpy
import re
from datetime import datetime

class Toolbox(object):
    def __init__(self):
        self.label = "NSW Project Tools"
        self.alias = "nswprojecttools"
        self.tools = [CreateSiteByLots]

class CreateSiteByLots(object):
    def __init__(self):
        self.label = "Create Site by Lots (Portal)"
        self.description = "Creates a site polygon, retires old versions in the Portal service, and appends the new site."
        self.canRunInBackground = False

    def getParameterInfo(self):
        # Param 0: Lot and Plan List
        param0 = arcpy.Parameter(
            displayName="Lot and Plan List",
            name="lot_plan_list",
            datatype="GPValueTable",
            parameterType="Required",
            direction="Input"
        )
        param0.columns = [['GPString', 'Lot Number'], ['GPString', 'Plan Number']]

        # Param 1: Project Number
        param1 = arcpy.Parameter(
            displayName="Project Number",
            name="project_number",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )

        # Param 2: Project Description
        param2 = arcpy.Parameter(
            displayName="Project Description",
            name="description",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )

        # Removed Output Feature Class parameter as it is now hardcoded to the service.

        return [param0, param1, param2]

    def isLicensed(self):
        return True

    def execute(self, parameters, messages):
        # Helper to safely embed user text inside SQL string literals
        def _escape_sql_literal(val):
            if val is None:
                return ""
            # Double any single quotes to prevent breaking out of the literal
            return str(val).replace("'", "''").strip()

        # --- CONFIGURATION ---
        # NSW Spatial Services (Source)
        source_url = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer/8"
        
        # Your Project Service (Target)
        # Note: We append '/0' to ensure we are targeting the first layer in the service
        target_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"
        
        # TARGET FIELD MAPPING (Update these if your service field names differ)
        f_proj_num = "project_number"
        f_desc     = "ProjectName"
        f_end_date = "EndDate"
        f_area     = "Area_Ha"
        
        # ---------------------

        # 1. Retrieve User Inputs
        lot_plan_table = parameters[0].value
        proj_num_raw = parameters[1].valueAsText
        proj_desc_raw = parameters[2].valueAsText

        # Validate project number explicitly; Required in the UI is not
        # sufficient to guarantee a non-empty value here.
        if proj_num_raw is None or not str(proj_num_raw).strip():
            messages.addErrorMessage("Project Number is required and cannot be blank.")
            return

        # Validate project description explicitly for consistency with project number
        if proj_desc_raw is None or not str(proj_desc_raw).strip():
            messages.addErrorMessage("Project Description is required and cannot be blank.")
            return

        # Clean versions used for attribute values, escaped version only for SQL
        proj_num = str(proj_num_raw).strip()
        proj_num_sql = _escape_sql_literal(proj_num)
        proj_desc = str(proj_desc_raw).strip()
        
        # 2. Build SQL for NSW Data
        messages.addMessage("Constructing query for NSW Spatial Services...")
        where_clauses = []
        
        if lot_plan_table:
            for row in lot_plan_table:
                raw_lot = _escape_sql_literal(row[0])
                raw_plan = str(row[1]).strip()
                clean_plan = re.sub(r'\D', '', raw_plan)  # Remove DP/SP

                # Validate both lot and plan are non-empty before building SQL clause
                if not raw_lot or not clean_plan:
                    continue

                # Safely escape and quote both lot and plan values for SQL.
                clean_plan_sql = _escape_sql_literal(clean_plan)
                clause = f"(lotnumber = '{raw_lot}' AND plannumber = '{clean_plan_sql}')"
                where_clauses.append(clause)
            
            if not where_clauses:
                messages.addErrorMessage("No valid Lot/Plan inputs.")
                return
            full_where_clause = " OR ".join(where_clauses)
        else:
            messages.addErrorMessage("No inputs provided.")
            return

        # 3. Create Geometry (In Memory)
        temp_layer = "temp_nsw_parcels"
        mem_dissolve = "memory/dissolved_site"
        target_layer_name = None  # Initialize before try block to avoid NameError in finally
        
        try:
            if arcpy.Exists(temp_layer): arcpy.management.Delete(temp_layer)
            if arcpy.Exists(mem_dissolve): arcpy.management.Delete(mem_dissolve)

            # Query Source
            messages.addMessage("Fetching geometry...")
            arcpy.management.MakeFeatureLayer(source_url, temp_layer, full_where_clause)
            
            count = int(arcpy.management.GetCount(temp_layer).getOutput(0))
            if count == 0:
                messages.addErrorMessage("No lots found. Please check your numbers.")
                return
            
            # Dissolve
            arcpy.management.Dissolve(temp_layer, mem_dissolve, multi_part="MULTI_PART")
            
            # 4. Calculate Area (Geodesic Hectares)
            # We grab the geometry object directly to calculate area before insertion
            new_geom = None
            area_ha = 0.0

            with arcpy.da.SearchCursor(mem_dissolve, ["SHAPE@"]) as s_cursor:
                for row in s_cursor:
                    new_geom = row[0]
                    # Calculate Geodesic Area in Hectares
                    area_ha = new_geom.getArea("GEODESIC", "HECTARES")
                    break  # Should only be one feature after dissolve

            # Ensure we actually obtained a geometry before proceeding.
            if new_geom is None:
                messages.addErrorMessage(
                    "Dissolve output did not produce a valid geometry. "
                    "Cannot create or upload a site polygon."
                )
                return

            messages.addMessage(f"Site Area Calculated: {round(area_ha, 4)} Ha")

            # 5. Connect to Target Service
            # We create a layer for the target service to enable editing interactions
            target_layer_name = "target_service_layer"
            if arcpy.Exists(target_layer_name): arcpy.management.Delete(target_layer_name)
            
            arcpy.management.MakeFeatureLayer(target_url, target_layer_name)

            # 6. Check for Existing Project and Update (Retire)
            # Query: ProjectNumber matches AND EndDate is NULL
            # proj_num_sql has been escaped for safe single-quoted use.
            check_query = f"{f_proj_num} = '{proj_num_sql}' AND {f_end_date} IS NULL"
            
            messages.addMessage(f"Checking for existing active records for {proj_num}...")
            
            # We select the specific records to update
            arcpy.management.SelectLayerByAttribute(target_layer_name, "NEW_SELECTION", check_query)
            match_count = int(arcpy.management.GetCount(target_layer_name).getOutput(0))
            
            if match_count > 0:
                messages.addMessage(f"Found {match_count} active record(s). Retiring them (Setting EndDate)...")
                current_time = datetime.now()
                
                # Update the EndDate
                with arcpy.da.UpdateCursor(target_layer_name, [f_end_date]) as u_cursor:
                    for row in u_cursor:
                        row[0] = current_time
                        u_cursor.updateRow(row)
            else:
                messages.addMessage("No active previous versions found.")

            # 7. Insert New Record
            messages.addMessage("Uploading new site to Feature Service...")
            
            # Fields to insert: Shape, ProjectNum, Description, AreaHa
            insert_fields = ["SHAPE@", f_proj_num, f_desc, f_area]
            
            with arcpy.da.InsertCursor(target_layer_name, insert_fields) as i_cursor:
                # Use the clean (unescaped) project number for attribute storage.
                i_cursor.insertRow([new_geom, proj_num, proj_desc, area_ha])

            messages.addMessage("Success! Site uploaded and area updated.")

        except arcpy.ExecuteError:
            messages.addErrorMessage(arcpy.GetMessages(2))
        except Exception as e:
            messages.addErrorMessage(f"An unexpected error occurred: {str(e)}")
        finally:
            # Clean up
            if arcpy.Exists(temp_layer): arcpy.management.Delete(temp_layer)
            if arcpy.Exists(mem_dissolve): arcpy.management.Delete(mem_dissolve)
            if target_layer_name is not None and arcpy.Exists(target_layer_name):
                arcpy.management.Delete(target_layer_name)

        return
