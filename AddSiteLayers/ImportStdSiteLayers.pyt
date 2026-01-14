# ImportStdSiteLayers.pyt
# ArcGIS Python toolbox that wraps ImportStdSiteLayers.run_import_std_site_layers
# This toolbox provides the GUI/parameters, calls the refactored script, and reports results via arcpy.AddMessage/Errors.

import arcpy
import os
import sys

# Ensure the script's directory is on sys.path so we can import ImportStdSiteLayers
TOOL_DIR = os.path.dirname(__file__) if '__file__' in globals() else os.getcwd()
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

try:
    import ImportStdSiteLayers as import_std_mod
except Exception:
    import_std_mod = None

class Toolbox(object):
    def __init__(self):
        self.label = "Import Standard Site Layers (Split Step 2)"
        self.alias = "ImportStdSiteLayers"
        self.tools = [ImportStdSiteLayersTool]

class ImportStdSiteLayersTool(object):
    def __init__(self):
        self.label = "Import Standard Site Layers"
        self.description = "Adds standard project layers based on the subject site (Step 2, refactored)."
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

        param1 = arcpy.Parameter(
            displayName="Overwrite existing project data",
            name="overwrite_existing",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param1.value = False

        param2 = arcpy.Parameter(
            displayName="Force re-query even if output exists (refresh)",
            name="force_requery",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param2.value = False

        return [param0, param1, param2]

    def updateParameters(self, parameters):
        # Attempt to refresh the project number list from the service like the original toolbox did.
        try:
            if import_std_mod and hasattr(import_std_mod, "_get_token"):
                token = import_std_mod._get_token()
                target_layer_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"
                params = {"where": "EndDate IS NULL", "outFields": "project_number", "returnDistinctValues": "true", "f": "json"}
                if token:
                    params["token"] = token
                query_url = f"{target_layer_url}/query?{urllib.parse.urlencode(params)}"
                try:
                    with urllib.request.urlopen(query_url, timeout=30) as resp:
                        data = json.loads(resp.read().decode())
                    values = sorted({str(feat['attributes'].get('project_number')) for feat in data.get('features', []) if feat['attributes'].get('project_number') is not None})
                    parameters[0].filter.list = values
                    if parameters[0].valueAsText and parameters[0].valueAsText in values:
                        parameters[0].value = parameters[0].valueAsText
                except Exception:
                    # Silently ignore refresh failures to avoid blocking the UI
                    pass
        except Exception:
            pass
        return

    def updateMessages(self, parameters):
        p_proj_num = parameters[0]
        if p_proj_num.altered:
            val = p_proj_num.valueAsText
            if val and (not val.isdigit() or len(val) > 5):
                p_proj_num.setErrorMessage("Project Number must be 5 digits or less (numeric).")
        return

    def isLicensed(self):
        return True

    def execute(self, parameters, messages):
        if import_std_mod is None:
            arcpy.AddError("Could not import ImportStdSiteLayers.py. Ensure the script is in the same folder as this toolbox.")
            return

        project_number = parameters[0].valueAsText
        overwrite_flag = bool(parameters[1].value) if len(parameters) > 1 else False
        force_requery = bool(parameters[2].value) if len(parameters) > 2 else False

        arcpy.AddMessage("Calling ImportStdSiteLayers.run_import_std_site_layers(...)")
        try:
            res = import_std_mod.run_import_std_site_layers(project_number, overwrite_flag=overwrite_flag, force_requery=force_requery)
            arcpy.AddMessage(f"ImportStdSiteLayers result: {res}")
            if not res.get("success"):
                arcpy.AddError("ImportStdSiteLayers reported failure. Check messages above.")
        except Exception as e:
            arcpy.AddError(f"Error running ImportStdSiteLayers: {e}\n{traceback.format_exc()}")
        return
