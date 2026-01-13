import arcpy
import os
import json

class Toolbox(object):
    def __init__(self):
        self.label = "Corporate Style Enforcer"
        self.alias = "HeadmasterStyles"
        self.tools = [BodySnatcherStyle]

class BodySnatcherStyle(object):
    def __init__(self):
        self.label = "Apply Style (The Body Snatcher)"
        self.description = "Replaces the target layer with the Style File, re-wiring the data source."
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Layer to Replace (Target)",
            name="in_layer",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Corporate Style File (Source)",
            name="style_file",
            datatype="DEFile",
            parameterType="Required",
            direction="Input")
        param1.filter.list = ['lyrx']
        
        corporate_path = r"G:\Shared drives\99.3 GIS Admin\Production\Layer Files"
        if os.path.exists(corporate_path):
            param1.value = corporate_path

        return [param0, param1]

    def inspect_json(self, style_path):
        """ robust inspector that handles Simple Renderers """
        try:
            with open(style_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Navigate nested structure
            layer_defs = data.get("layerDefinitions", [])
            if not layer_defs: return "Error: Invalid .lyrx file (No definitions)"
            
            first_layer = layer_defs[0]
            renderer = first_layer.get("renderer", {})
            r_type = renderer.get("type", "Unknown").replace("CIM", "")
            
            info = [f"Renderer Type: {r_type}"]
            
            # Check labels
            if first_layer.get("showLabels"):
                info.append("Labels: ON")
            else:
                info.append("Labels: OFF")
                
            return " | ".join(info)
        except Exception as e:
            return f"Inspection Failed: {str(e)}"

    def execute(self, parameters, messages):
        target_layer_param = parameters[0].value
        target_layer_name = parameters[0].valueAsText
        style_file = parameters[1].valueAsText

        self.speak(f"Initiating replacement protocol for '{target_layer_name}'...", "INFO")

        # 1. INSPECT THE FILE
        # We print this immediately so you can see what is in the file
        file_stats = self.inspect_json(style_file)
        self.speak(f"Style File Contents: [{file_stats}]", "INFO")

        # 2. GET THE MAP AND TARGET
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        m = aprx.activeMap
        
        target_layer = None
        for l in m.listLayers():
            if l.longName == target_layer_name or l.name == target_layer_name:
                target_layer = l
                break
        
        if not target_layer:
            self.speak(f"Could not find layer '{target_layer_name}'.", "ERROR")
            return

        try:
            # 3. CAPTURE DATA CONNECTION
            # We need to know where the current data lives so we can point the new layer to it.
            self.speak("analyzing current data connection...", "INFO")
            conn_props = target_layer.connectionProperties
            
            # Capture Definition Query (to preserve filters)
            def_query = target_layer.definitionQuery
            
            # 4. BRING IN THE REPLACEMENT (The Style File)
            self.speak("Importing Corporate Style...", "INFO")
            # This adds the .lyrx to the map. It will usually point to a broken link initially.
            imported_layers = m.addDataFromPath(style_file)
            
            # addDataFromPath returns the added layer (or a group layer)
            if not imported_layers:
                self.speak("Failed to add style file to map.", "ERROR")
                return
                
            new_layer = imported_layers # It's usually a single layer object
            
            # If the .lyrx contained a Group, we need to find the sub-layer
            if new_layer.isGroupLayer:
                # Assuming the style file is a single layer inside a group or just the layer
                # We take the first child
                new_layer = new_layer.listLayers()[0]

            # 5. REWIRE THE BRAIN (Update Data Source)
            self.speak("Rewiring data source to match your data...", "INFO")
            # We tell the new layer: "Use the connection properties of the old layer"
            new_layer.updateConnectionProperties(new_layer.connectionProperties, conn_props)
            
            # 6. RESTORE MEMORY (Definition Queries)
            if def_query:
                self.speak(f"Restoring definition query: {def_query}", "INFO")
                new_layer.definitionQuery = def_query

            # 7. CLEANUP (Remove the old layer)
            self.speak("Disposing of the obsolete layer...", "INFO")
            m.removeLayer(target_layer)
            
            # Rename new layer to match the old name
            new_layer.name = target_layer_name.split("\\")[-1] # Simple name

            self.speak("Replacement complete. The layer is now fully compliant.", "INFO")

        except Exception as e:
            self.speak("The transplant failed.", "ERROR")
            self.speak(str(e), "ERROR")

    def speak(self, message, severity):
        prefix = "Headmaster: "
        if severity == "INFO": arcpy.AddMessage(prefix + message)
        elif severity == "WARNING": arcpy.AddWarning(prefix + message)
        elif severity == "ERROR": arcpy.AddError(prefix + message)
