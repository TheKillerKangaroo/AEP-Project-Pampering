```python
# CreateSiteByProperty.pyt
# ArcGIS Python toolbox that wraps CreateSiteByProperty.run_create_site
# This toolbox provides the GUI/parameters, calls the refactored script, and reports results via arcpy.AddMessage/Errors.

import arcpy
import os
import sys

# Ensure the script's directory is on sys.path so we can import CreateSiteByProperty
# If this toolbox is deployed in the same folder as CreateSiteByProperty.py this will work.
TOOL_DIR = os.path.dirname(__file__) if '__file__' in globals() else os.getcwd()
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

try:
    import CreateSiteByProperty as create_site_mod
except Exception:
    create_site_mod = None

class Toolbox(object):
    def __init__(self):
        self.label = "Create Site By Property (Split Step 1)"
        self.alias = "CreateSiteByProperty"
        self.tools = [CreateSiteByPropertyTool]

class CreateSiteByPropertyTool(object):
    def __init__(self):
        self.label = "Create Site By Property"
        self.description = "Creates a standardized subject site polygon from an NSW address and writes it to the feature service (Step 1, refactored)."
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Address Search (Type and press Tab)",
            name="search_text",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

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
            displayName="Overwrite existing project data (Step 2)",
            name="overwrite_existing",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param4.value = False

        param5 = arcpy.Parameter(
            displayName="Run Step 2 automatically after Step 1 (NOT IMPLEMENTED)",
            name="run_step2_automatically",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param5.value = False
        param5.tooltip = ("This toolbox currently does not auto-run Step 2. "
                          "Use the existing 'Step 2 - Add Standard Project Layers' tool after this completes.")

        param6 = arcpy.Parameter(
            displayName="Force re-query even if output exists (refresh)",
            name="force_requery",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param6.value = False

        return [param0, param1, param2, param3, param4, param5, param6]

    def updateParameters(self, parameters):
        # Provide address suggestions if the CreateSiteByProperty module exposes _get_suggestions
        try:
            if create_site_mod and hasattr(create_site_mod, "_get_suggestions"):
                p_search = parameters[0]
                p_select = parameters[1]
                if p_search.altered and p_search.valueAsText and len(p_search.valueAsText) > 3:
                    token = None
                    try:
                        token = create_site_mod._get_token()
                    except Exception:
                        token = None
                    try:
                        suggestions = create_site_mod._get_suggestions(p_search.valueAsText, token)
                        if suggestions:
                            p_select.filter.list = suggestions
                            if not p_select.valueAsText:
                                p_select.value = suggestions[0]
                        else:
                            p_select.filter.list = []
                    except Exception:
                        pass
        except Exception:
            pass
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

    def isLicensed(self):
        return True

    def execute(self, parameters, messages):
        if create_site_mod is None:
            arcpy.AddError("Could not import CreateSiteByProperty.py. Ensure the script is in the same folder as this toolbox.")
            return

        site_address = parameters[1].valueAsText
        project_number = parameters[2].valueAsText
        project_name = parameters[3].valueAsText
        overwrite_flag = bool(parameters[4].value) if len(parameters) > 4 else False
        run_step2_flag = bool(parameters[5].value) if len(parameters) > 5 else False
        force_requery = bool(parameters[6].value) if len(parameters) > 6 else False

        arcpy.AddMessage("Calling CreateSiteByProperty.run_create_site(...)")
        try:
            res = create_site_mod.run_create_site(site_address, project_number, project_name,
                                                 overwrite_flag=overwrite_flag,
                                                 run_step2_flag=run_step2_flag,
                                                 force_requery=force_requery)
            arcpy.AddMessage(f"CreateSiteByProperty result: {res}")
            if not res.get("success"):
                arcpy.AddError("CreateSiteByProperty reported failure. Check messages above.")
        except Exception as e:
            arcpy.AddError(f"Error running CreateSiteByProperty: {e}\n{traceback.format_exc()}")
        return