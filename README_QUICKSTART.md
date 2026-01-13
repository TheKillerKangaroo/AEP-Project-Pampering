# AEP Project Framework — Quickstart

This is a lightweight quickstart for running the AEP Project Framework tools inside ArcGIS Pro.

Prerequisites
- ArcGIS Pro 3.6+ (run inside the ArcGIS Pro Python/runtime)
- Signed in to ArcGIS Online / Portal in ArcGIS Pro (the toolbox uses arcpy.GetSigninToken())
- Internet access to query:
  - Esri World Geocode service
  - NSW cadastre service (portal.spatial.nsw.gov.au)
  - Project feature services (configured in the script)
- Place your standard LYRX symbology file and update LAYERFILE_PATH in the script if required.

Install
1. Open ArcGIS Pro.
2. In the Catalog pane, right-click "Toolboxes" → Add Toolbox → select `AEP_Project_Framework_v4.0.pyt`.

Run — typical flow
1. Run "Step 1 - Create Subject Site"
   - Address Search: type an address and press Tab (suggestions appear).
   - Select Exact Address: pick from the dropdown.
   - Project Number and Project Name: fill in as required.
   - Decide whether to run Step 2 automatically and whether to overwrite existing project data.
   - The tool will:
     - Geocode the address
     - Select the cadastral parcel (CONTAINS → buffered INTERSECT fallback)
     - Compute area, populate attributes, append to the Project Study Area feature service
     - Optionally run Step 2

2. If Step 2 runs (or to run standalone), use "Step 2 - Add Standard Project Layers"
   - Choose a Project Number from the dropdown.
   - Set Overwrite / Force re-query options.
   - The tool will:
     - Retrieve the active Study Area (EndDate IS NULL)
     - Query the reference table for standard connections
     - Buffer/select/extract referenced layers into the project geodatabase
     - Add styled layers to a "Site Details Map"

Tips
- If you want consistent symbology, set `LAYERFILE_PATH` at the top of the .pyt to point to your LYRX file.
- Check Geoprocessing messages for details and tracebacks if something fails.
- Temporary items use prefixes like `temp_`, `tmp_extract_`, `temp_dissolved_` and are cleaned up at the end; manually delete leftovers if necessary.

If you want a full README with configuration details, contribution guidelines and templates, see the other repository files (CONTRIBUTING.md, ISSUE_TEMPLATE.md and LYRX_INSTRUCTIONS.md).