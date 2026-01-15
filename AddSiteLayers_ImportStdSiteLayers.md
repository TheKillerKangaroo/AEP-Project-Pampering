# Import Standard Site Layers

A short helper script-tool (ArcGIS Python Toolbox) that imports standard site layers for a selected project study area from ArcGIS Online services into the project's geodatabase.

This document explains what the tool does, its requirements, parameters, expected outputs, and troubleshooting tips.

---

## Overview

ImportStdSiteLayers:
- Queries a Project Study Area service to select a study area by Project Number.
- Reads a remote "Reference Table" that lists standard datasets (short name, service URL, buffer distance, sort order, desired feature dataset, and a friendly alias).
- For each listed layer:
  - Applies an optional buffer around the selected study area.
  - Performs a spatial selection (soft clip) against the remote service.
  - Downloads intersecting features into memory, then hard-clips them to the buffered study area.
  - Writes the clipped features into the project's geodatabase (creates feature datasets if specified).
  - Attempts to set the feature class alias (if license permits).
- Reports a summary of created, skipped, and failed layers.

The tool is intentionally friendly — it prints a random "dad joke" occasionally.

---

## Requirements

- ArcGIS Pro (or ArcGIS environment with arcpy).
- The script runs as a Python Toolbox (`.pyt`) tool inside ArcGIS Pro (or any environment where `arcpy.mp.ArcGISProject("CURRENT")` is available). If an ArcGIS Project is not open, the tool falls back to `arcpy.env.workspace`.
- Network access to the configured ArcGIS Feature Services:
  - Project Study Area: https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0
  - Reference Table: https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15
- Appropriate permissions to read those services and to write to the project's default geodatabase.

---

## Parameters (Tool dialog)

1. Project Number (choose Study Area)
   - Type: GPString (ValueList)
   - Required: Yes
   - Behavior: Populated from the Project Study Area service (`project_number` field). Pick the desired project/study area.

2. Overwrite existing project data
   - Type: GPBoolean
   - Optional. Default: False
   - Behavior: If False and an output feature class already exists, that layer will be skipped. If True, existing outputs will be deleted/recreated.

3. Force re-query even if output exists (refresh)
   - Type: GPBoolean
   - Optional. Default: False
   - Behavior: If True, the tool will re-query the source service and overwrite the existing output even if it exists (useful when you want updated features).

---

## Important behavior & configuration

- Default geodatabase:
  - The tool attempts to use the current ArcGIS Project's default geodatabase (`aprx.defaultGeodatabase`). If no ArcGIS Project is open, it uses `arcpy.env.workspace`.
  - If a Reference Table entry specifies a `FeatureDatasetName`, the tool will attempt to create (or reuse) a feature dataset with that name (sanitized).

- Spatial reference:
  - The tool creates feature datasets using spatial reference EPSG/ID 8058 (GDA2020 NSW Lambert). This may influence reprojection behavior for source layers — you should ensure compatibility or modify the script if necessary.

- License awareness:
  - On Basic (ArcView) license level the script avoids operations that may fail due to license limits (notably altering alias names). On Standard/Advanced, the tool attempts to set the feature class alias from the reference table.

- Temporary storage:
  - The tool uses in-memory feature classes (memory\...) for intermediate clipping and copies. Temporary items are deleted as processing proceeds.

- Reference Table filter:
  - The tool reads rows where `ProjectType = 'all'` and applies ordering by `SortOrder`. If you want a custom subset, you can edit the script or the reference table.

---

## Expected outputs

- One or more feature classes written into:
  - The project's default geodatabase, or
  - Inside new/existing Feature Datasets if `FeatureDatasetName` is specified for a layer (the script sanitizes dataset and layer names to remove spaces/special characters).
- Messages in the geoprocessing pane indicating:
  - How many layers were imported, skipped, or failed.
  - Warnings for geometry-related issues (see troubleshooting).

---

## Example usage

- In ArcGIS Pro:
  1. Add the Python Toolbox `ImportStdSiteLayers.pyt` to your project's Catalog.
  2. Open the tool.
  3. Choose the Project Number from the dropdown (populated from the Project Study Area service).
  4. Select `Overwrite existing project data` if you want to replace outputs.
  5. Check `Force re-query` if you need to re-download sources even when outputs already exist.
  6. Run and monitor messages.

- As a script in an environment with an open ArcGIS Pro project:
  - Use the toolbox GUI; the code is designed for use as a toolbox tool rather than a standalone script.

---

## Troubleshooting & common messages

- "Please select a valid Project Number."
  - Meaning: The selected value in the Project Number dropdown is not valid (e.g., the dropdown showed "No Projects Found" or an ERROR text). Make sure the Project Study Area service is reachable and contains a `project_number` attribute.

- "CRITICAL: Project <number> is playing hide and seek (and winning). Not found."
  - Meaning: No feature in the Project Study Area service matched the chosen `project_number`. Confirm the value and service contents.

- Geometry/processing failures:
  - The script catches generic exceptions. If you see warnings mentioning "geometry gremlins" or geoprocessing code errors (for example "999999" or "000117"), the issue is usually with source geometry or service timeouts. Try:
    - Increasing the study area buffer or using smaller buffer values.
    - Re-running with `Force re-query` checked.
    - Running the problematic service layer directly in Pro to inspect geometry/topology.

- Alias changes not applied:
  - Alias renaming requires Standard/Advanced license. The tool detects Basic (ArcView) and skips alias renaming silently. If you expect aliases and they are not being set, check your license level.

- No features found for a layer:
  - The tool reports "Ghost town. No features found here." That means the remote service had no features intersecting the (buffered) study area; nothing is written to the geodatabase.

- Reference table read failure:
  - If the reference table URL is unreachable or its schema changed (missing fields like `ShortName`, `URL`, `SiteBuffer`, `SortOrder`, `FeatureDatasetName`, `FieldAlias`), the tool will fail to build the list. Verify the table schema and URL.

---

## Customization tips

- Change services:
  - The script hard-codes the Project Study Area and Reference Table URLs near the top of `run_import_std_site_layers()`. Update those values if you have alternate services.

- Spatial reference:
  - To change the target spatial reference, modify `target_sr = arcpy.SpatialReference(8058)`.

- Buffers and selection logic:
  - The script applies a buffer per the `SiteBuffer` field (meters). If you want alternate units or behavior, modify the buffer creation and clip logic.

- Logging:
  - The tool uses `arcpy.AddMessage`, `AddWarning`, and `AddError` to surface progress. You can augment these or write to a log file if desired.

---

## Known limitations

- Designed for online Feature Services that can be used in MakeFeatureLayer operations. If a service requires authentication or uses a non-standard schema, adapt the script.
- Uses the ArcGIS Project default geodatabase; the script does not accept a dedicated output GDB parameter (edit the script to add a parameter if needed).
- Feature dataset creation will fail if the chosen spatial reference is incompatible with existing datasets — the script attempts a safe fallback but you should confirm CRS expectations.

---

## Contact / Attribution

- Tool author: See repository `TheKillerKangaroo/AEP-Project-Pampering`.
- For issues with the code or behavior, open an issue in the repository with the full geoprocessing messages and a sample Project Number.

---

### Quick changelog (embedded)
- Initial behaviour: reads reference table, clips by study area buffer, creates outputs in default gdb, attempts aliasing when allowed.

---

Thanks for using ImportStdSiteLayers — may your layers always clip cleanly and your geodatabases remain uncorrupted. 🎯