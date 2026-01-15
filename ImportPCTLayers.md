# ImportPCTLayers Tool — Documentation

Overview
--------
"Import Standard Site Layers" is a geoprocessing tool implemented in the ImportPCTLayers.pyt toolbox. It downloads site-specific feature data from configured ArcGIS REST services for a chosen Project Study Area (PSA), clips features to the project's extent (optionally buffered), saves them into the project's geodatabase (optionally into a named Feature Dataset), and exports layer files (.lyrx) that preserve the service symbology for quick use in ArcGIS Pro maps.

Source code (for reference):
- Import script: [AddPCTLayers/ImportPCTLayers.pyt](https://github.com/TheKillerKangaroo/AEP-Project-Pampering/blob/225505c13567f75eaf82cfc63f31935e32c1cf5f/AddPCTLayers/ImportPCTLayers.pyt)

Requirements
------------
- ArcGIS Pro (arcpy) — the tool is built for ArcGIS Pro's arcpy.mp/arcpy.management APIs.
- Network access to the configured ArcGIS REST services:
  - Project Study Area service
  - Standard Connection Reference Table service
  - Any other services referenced by the Reference Table
- Write access to the ArcGIS Pro project default geodatabase and project folder.
- Optional: Signed-in ArcGIS account in Pro (the tool will attempt to use arcpy.GetSigninToken() to access token-protected services).

What the tool does (high level)
-------------------------------
1. Presents a Project Number picker (populated from the Project Study Area service).
2. Finds the PSA and copies it to memory.
3. Reads the Reference Table (service URL is in the script) to gather a list of layers to import for the "pct" project type.
4. For each layer entry:
   - Builds a query geometry (PSA or PSA buffered).
   - Queries the service for object IDs that intersect the query geometry (uses the REST /query endpoint directly with a token if available).
   - Downloads features in batches, with a single-feature rescue for failing batches.
   - Clips downloaded features to the PSA geometry and saves the result into the project's geodatabase (optionally inside a Feature Dataset).
   - Attempts to extract the service symbology and save a .lyrx file in a "Layers" folder adjacent to the geodatabase/project home.
   - Optionally alters the alias name for the output feature class (license permitting).
5. Emits a summary of imported, skipped, and failed layers and the folder where layer files were saved.

Parameters
----------
- Project Number (Project Study Area) — required (GPString)
  - Drop-down is populated from the Project_Study_Area FeatureServer. Pick the Project Number for which you want to import layers.
- Overwrite existing project data — optional (GPBoolean, default: False)
  - If checked, the tool will overwrite existing feature classes with the same name.
- Force re-query even if output exists (refresh) — optional (GPBoolean, default: False)
  - If checked, the tool will re-download features and replace existing outputs even when they already exist.

Expected outputs
----------------
- Feature classes saved to the active project default geodatabase (arcpy.mp.ArcGISProject("CURRENT").defaultGeodatabase) or to a Feature Dataset (if configured in the Reference Table).
- Corresponding .lyrx layer files saved in a "Layers" folder next to the project home folder (project home is the ArcGIS Pro project folder). If the folder cannot be created, the .lyrx files will be saved to the project home folder.
- Console (geoprocessing) messages summarizing:
  - Captured (new) layers
  - Ignored (skipped) layers
  - Exploded (failed) layers

Usage — Graphical (ArcGIS Pro)
------------------------------
1. Add the Python toolbox (.pyt) to ArcGIS Pro Catalog > Toolboxes.
2. Open the toolbox and run "Import Standard Site Layers".
3. Select a Project Number from the dropdown (populated from the Project Study Area service).
4. Optionally enable "Overwrite existing project data" and/or "Force re-query (refresh)".
5. Click Run and monitor the Geoprocessing pane messages.

Usage — Python (scripting)
--------------------------
You can run this toolbox from a Python script within the same ArcGIS Pro session. Example:

```
import arcpy

# Load the toolbox (adjust path to where the .pyt file is located)
toolbox_path = r"C:\Path\To\AddPCTLayers\ImportPCTLayers.pyt"
arcpy.ImportToolbox(toolbox_path)

# Call the tool: arcpy.<ToolClassName>_<toolbox_alias>(params...)
# The toolbox sets alias = "project_creation" and the tool class name is ImportStdSiteLayersTool
# Example: Project Number "12345", overwrite=True, force_refresh=False
arcpy.ImportStdSiteLayersTool_project_creation("12345", True, False)
```

Notes:
- The exact callable name may vary depending on how ArcGIS registers the tool; use the tool name that appears in the Catalog if needed.
- Run the script from within ArcGIS Pro (so the CURRENT project and default geodatabase are available), or adjust the script to open a specific APRX file and supply different workspace paths.

Troubleshooting
---------------
- The Project Number list is empty or shows "No Projects Found" / "ERROR":
  - Ensure you have network access to the configured Project_Study_Area FeatureServer endpoint.
  - Check that the service URL in the script is reachable; the script queries:
    https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0
- "CRITICAL: Project X not found." error:
  - Confirm the Project Number you selected exists in the Project_Study_Area service and that you chose the correct value from the dropdown.
- Nothing downloads for a layer (0 objectIds):
  - Confirm the Reference Table contains a valid service URL for the layer.
  - Check that the layer actually has features within the project's bounding geometry (consider the configured buffer).
- Permission or write errors when saving to the default geodatabase:
  - Verify the ArcGIS Pro project's default geodatabase path is writable and not read-only.
- Symbology extraction fails:
  - Some services may not expose drawing information or the drawing info may be incompatible. The tool will still save the feature class even if creating the .lyrx fails.
- Token / Authentication problems:
  - The tool tries to use arcpy.GetSigninToken() to fetch a token for private services. If you are not signed into ArcGIS Online/Portal in ArcGIS Pro, the tool will attempt anonymous queries. The script also disables SSL verification for direct urllib calls — this can help in environments with certificate issues but has security trade-offs.
- Long-running operations:
  - The tool fetches features in batches (default BATCH_SIZE=20) and uses an in-memory workspace for merging before saving. For very large layers this may be time-consuming or memory-intensive — consider running for one or a few layers at a time, or increasing batch size if the network is stable.

Implementation notes & limitations
---------------------------------
- Runs in foreground only (canRunInBackground = False).
- Uses in-memory workspace names like memory\primary_clip_boundary and memory\merged_download. If ArcGIS Pro's memory workspace is limited, large downloads could fail.
- The script explicitly disables SSL certificate verification for urllib requests (ssl.CERT_NONE). This makes it tolerant of certificate issues but is less secure — be aware of the environment.
- Alias renaming is skipped for ArcView license level; the script checks the product license and only attempts AlterAliasName when allowed.
- The Reference Table URL and Project Study Area URL are hard-coded in the script. If your environment uses different service URLs, update the .pyt script accordingly.
- The tool saves .lyrx layer files as RELATIVE. If you move the layer file, you may need to repair data source paths in ArcGIS Pro.

Recommended edits (if you want to customize)
--------------------------------------------
- Update service URLs to local/organization endpoints if necessary.
- Make BATCH_SIZE configurable via a tool parameter if you frequently hit transfer or memory limits.
- Remove (or make conditional) the SSL verification bypass in production environments.
- Add logging to a file as well as to geoprocessing messages for long runs or automation scenarios.

Change log / authorship
-----------------------
- Based on the ImportPCTLayers.pyt script in this repository.
- Created by: TheKillerKangaroo (repository owner)
- Date: 2026-01-15

Contact / help
--------------
If you need improvements or run into issues not covered here, open an issue in the repository or contact the repository owner for assistance.
