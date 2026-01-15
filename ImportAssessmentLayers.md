# Import Standard Site Layers (ImportAssessmentLayers)

Tool script: `AddAssessmentLayers/ImportAssessmentLayers.pyt`  
Tool name in ArcGIS Pro: **Import Standard Site Layers**  
Tool label: "Import Standard Site Layers"  
Description: Imports site layers for a selected project study area from hosted ArcGIS Feature Services, downloads features that intersect the study area (optionally buffered), saves feature classes into the project's geodatabase (optionally within a feature dataset), and extracts symbology into .lyrx files saved to a "Layers" folder next to the project.

---

## Overview

This geoprocessing script automates bringing in "standard" site datasets for a chosen project study area. For each selected Project Type the tool:

- Queries the reference table (hosted feature service) to get service URLs and metadata.
- Finds features that intersect the selected project's study area (with optional buffer).
- Downloads them in batches (with single-feature fallback for troublesome records).
- Clips the downloaded features to the (buffered) study area and saves as a local feature class in the project's default geodatabase (or inside a feature dataset if configured).
- Attempts to transfer symbology from the hosted service to the local layer and saves a .lyrx file into a `Layers` folder next to the project.

The tool uses a REST-based approach to fetch ObjectIDs first (with anonymous GET preferred, token fallback, POST fallback), then fetches features in batches (default batch size = 20). It writes useful messages, warnings, and a final summary of items created/skipped/failed.

---

## Requirements and prerequisites

- ArcGIS Pro environment (script expects to run in ArcGIS Pro / arcpy MP context). The script tries to use the open project (`CURRENT`) to determine:
  - project default geodatabase (target geodatabase)
  - project home folder (for `Layers` output)
- arcpy (installed with ArcGIS Pro)
- Network access to the hosted services referenced by the tool:
  - Standard Connection Reference Table (reference table):  
    https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15
  - Project Study Area service:  
    https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0
- If services are secured (private), sign in to ArcGIS Online / Portal in ArcGIS Pro so `arcpy.GetSigninToken()` can provide a token. The tool will try anonymous access first, then retry with the token if available.
- Sufficient disk space in the target geodatabase and the project folder for the layer files.

Note: The script disables certificate verification for HTTP(S) requests (creates SSL context with CERT_NONE) to improve compatibility with some hosts. If your environment enforces strict SSL policies, be aware of this behaviour.

---

## Tool parameters

1. Project Number (Required; ValueList)  
   - Choose the Project Number (study area) to import layers against. The list is populated from the Project_Study_Area service.
2. Additional Project Types to Import (Optional; Multi-value ValueList)  
   - Multiselect list of ProjectType values read from the reference table. Only rows with ProjectType matching selected values will be processed. (Rows with ProjectType `all` or `pct` are excluded from the list.)
   - If you select nothing, the tool exits early (no types processed).
3. Overwrite existing project data (Optional; Boolean)  
   - If False and a target feature class already exists, the tool will skip that layer. If True, existing outputs will be overwritten.
4. Force re-query even if output exists (refresh) (Optional; Boolean)  
   - If True, the tool will re-download and re-create outputs even if the feature class exists (acts like an explicit refresh).

---

## Outputs

- Feature classes saved to the project's default geodatabase (or a feature dataset if `FeatureDatasetName` is specified in the reference table). Names are normalized (spaces/dashes → underscores; non-alphanumeric chars removed).
- .lyrx layer files saved to a `Layers` folder placed next to the project's home folder (e.g., if project home is `C:\Projects\MyProject`, the .lyrx files go into `C:\Projects\MyProject\Layers`).
- Messages, warnings, and a final summary printed in the tool log (counts for Captured / Ignored / Failed).

---

## How it works (operational details)

- Study area selection:
  - The tool creates a temporary feature layer from the Project Study Area service and selects the record with the provided `project_number`.
  - The selection is used as a clip boundary; if a buffer value is present in the reference table row, the clip is expanded by that buffer distance (in meters) before intersection queries and final clip.

- Reference table:
  - The reference table includes columns used by the tool: `ShortName`, `URL`, `SiteBuffer`, `SortOrder`, `FeatureDatasetName`, `FieldAlias`, `ProjectType`.
  - The tool reads rows that match the selected `ProjectType` values and processes them in `SortOrder`.

- Querying remote services:
  - The tool prefers anonymous GET requests to the service REST `/query` endpoint using the study area bounding box. If anonymous GET returns 403 and an ArcGIS sign-in token is available, it retries with a token. If GET is not permitted, it falls back to POST.
  - If no object IDs are returned for the study area bounding box, the layer is skipped.

- Download and save:
  - ObjectIDs are fetched and divided into batches (BATCH_SIZE = 20). For each batch the tool makes a temporary layer with a WHERE clause on the remote service and copies features to memory, then appends into a merged memory dataset.
  - If a batch fails, the tool attempts a single-feature rescue for each OID in that batch.
  - The merged memory feature set is clipped to the buffered study area and saved into the target geodatabase (or inside a feature dataset if specified).
  - When possible, the tool transfers symbology from the remote service layer to the local layer and saves a .lyrx file.

- Symbology:
  - Uses `ApplySymbologyFromLayer` between the hosted service layer and the local layer, then `SaveToLayerFile(..., "RELATIVE")` to write a .lyrx.

---

## Typical usage steps (ArcGIS Pro)

1. Open your ArcGIS Pro project (the script attempts to use the `CURRENT` project).
2. Launch the "Import Standard Site Layers" tool (from the toolbox where the `.pyt` has been added).
3. Select the Project Number (choose from the drop-down).
4. Choose one or more Additional Project Types (optional). If you do not select any types the tool will exit without processing.
5. Set the Overwrite and Force Refresh flags as needed.
6. Run the tool and watch the geoprocessing messages. When complete, check:
   - The default geodatabase for new feature classes (or the feature dataset specified in the reference table).
   - The `Layers` folder next to your project for .lyrx files.

---

## Troubleshooting and tips

- "Project not found" error:
  - Ensure the chosen Project Number exists in the Project_Study_Area service. If the Project Number list shows an "ERROR" message when populating the parameter list, check your network and service URL availability.
- No Project Types listed / no layers processed:
  - The "Additional Project Types" list is populated from the reference table. If you don't pick any, the tool will not process anything. Pick project types that match the `ProjectType` values in the reference table.
- Token and secured services:
  - If a service is secured, sign in to Portal/AGOL in ArcGIS Pro before running the tool so `arcpy.GetSigninToken()` can provide the token.
- ObjectIDs query failing:
  - The script tries anonymous GET, token GET, and POST fallbacks. If your organization blocks direct REST calls from Python or requires special headers, you may need to adjust network/proxy settings or run inside the organization's environment.
- Symbology extraction fails:
  - Sometimes hosted services have renderers or symbol types that are not transferable. The script will emit a warning and still save the data.
- Large datasets:
  - Batch size is small (20) to reduce memory/timeouts; for very large numbers of features the download may still be slow. Consider running with a larger geodatabase, more temporary disk, or running per-type.
- SSL/Certificate issues:
  - The script disables SSL certificate verification for HTTP requests (to improve compatibility). If your environment requires strict certificate checks, update the script to use proper CA verification.

---

## Known limitations

- If the reference table contains a `ProjectType` value of `all` or `pct`, those are intentionally excluded when populating selectable types.
- The tool will not create a project if no additional project types are selected — this is by design: the tool only imports additional types selected by the user.
- The script assumes the target geodatabase supports creating feature datasets. If creation of the dataset fails, the tool falls back to writing feature classes to the GDB root.
- OID field is probed via `MakeFeatureLayer` on the service; if that probe fails the script falls back to `OBJECTID` as a default OID field name.
- The script uses an insecure SSL context for REST calls (skips verification). If this is unacceptable for your environment, modify the script to validate certificates.

---

## Logging & messages

- The tool writes progress and warnings via `arcpy.AddMessage`, `arcpy.AddWarning`, and `arcpy.AddError`. At the end it prints a summary:
  - Captured: number of features/layers successfully saved
  - Ignored: skipped because outputs already existed (and overwrite not enabled) or no intersecting features
  - Exploded: number of failed layers

---

## File locations in repository

- Script file: `AddAssessmentLayers/ImportAssessmentLayers.pyt`  
  (the script that implements the tool logic and parameter definitions)

---

## Example run notes

- If you want to forcibly re-download and refresh existing outputs, check both `Overwrite existing project data` and `Force re-query even if output exists (refresh)`.
- If downloads are failing with HTTP 403 but you can access services from the Pro map, try signing out and back in to refresh tokens or sign in through the Account pane in ArcGIS Pro before running.

---

## Contact / Next steps

If you need:
- Additional logging (e.g., write a CSV with layer processing results),
- Increased batch size for performance tuning,
- Strict SSL verification support,
- Or more robust error handling for particular secured services,

open an issue in the repository or edit the `.pyt` and test in a development copy of your ArcGIS Pro project.
