# AEP Project Framework Toolbox (ArcGIS Pro)

ArcGIS Pro toolbox and script to create a standardized "Project Study Area" from an NSW address and to extract/add a set of standard project layers for environmental assessment work in New South Wales, Australia.

This repository includes `AEP_Project_Framework_v4.0.pyt` — a Python toolbox implementing two tools:
- Step 1 — Create Subject Site
- Step 2 — Add Standard Project Layers

The toolbox is written for ArcGIS Pro (tested with ArcGIS Pro 3.6+) and uses arcpy and ArcGIS REST services.

---

## Quick summary

- Purpose: Geocode an address, identify the cadastral parcel, create a standardized study-area polygon in your project feature service, and optionally extract a curated list of standard layers (buffering, selection, extracting) into your project's geodatabase and a dedicated "Site Details Map".
- Primary outputs:
  - Writes/updates a Project Study Area record to the Project_Study_Area feature service.
  - Optionally extracts many standard layers into the project's default geodatabase and adds them (styled) into a "Site Details Map".
- Requires network access to Esri World Geocode service and NSW spatial services.

---

## Requirements

- ArcGIS Pro 3.6 or later (the toolbox uses ArcGIS Pro's arcpy.mp APIs)
- Python/runtime provided by ArcGIS Pro (the toolbox uses arcpy — do not run in a plain Python environment)
- ArcGIS Pro sign‑in to access ArcGIS Online/Enterprise services (used to obtain tokens via arcpy.GetSigninToken())
- Internet access to query these services (examples used by the script):
  - World Geocode service (https://geocode-api.arcgis.com)
  - NSW Cadastre service (portal.spatial.nsw.gov.au)
  - Project feature services used by this project:
    - Project Study Area service (configured in the script)
    - Standard Connection Reference Table service (configured in the script)
- Optional: a local LYRX file to standardise styling (path declared in the script)

Note: The script expects to run inside an open ArcGIS Pro project (CURRENT).

---

## Installation / Usage

1. Open ArcGIS Pro.
2. In the Catalog pane, right-click "Toolboxes" -> Add Toolbox -> add `AEP_Project_Framework_v4.0.pyt` (this file).
3. Run the toolbox tools from the toolbox item or search by name in the Geoprocessing pane.

Tool parameters and typical workflow:

### Step 1 — Create Subject Site
- Address Search (text): type an NSW address (tab to trigger suggestions).
- Select Exact Address: choose an address suggestion.
- Project Number: numeric or text project identifier (used to set / query `project_number` on the feature service).
- Project Name: descriptive project name.
- Output Study Area: derived output (the created study area).
- Overwrite existing project data (Step 2): when Step 2 runs automatically, decides whether to overwrite outputs.
- Run Step 2 automatically after Step 1: if checked, Step 2 runs immediately using the created study area.
- Force re-query (refresh): forces re-query of services in Step 2 even if outputs already exist.

What the tool does:
- Geocodes the chosen address using Esri World Geocode service.
- Selects the cadastral parcel from NSW parcel service (first CONTAINS, then buffered INTERSECT fallback).
- Dissolves multi-part parcels, computes geodesic area, writes attributes (project number/name, geocoded address, area).
- Archives any existing active Project Study Area records for the same project number by writing `EndDate`.
- Appends the new study area to the configured Project_Study_Area feature service.
- Adds the study area to the active map and attempts to apply a standard LYRX symbology file if available (see configuration below).
- Optionally continues to Step 2 using the newly created study area.

### Step 2 — Add Standard Project Layers (standalone)
- Project Number (choose Study Area): selects an active study area from the service (dropdown is populated from the service).
- Overwrite existing project data: if true, existing outputs in the default geodatabase will be replaced.
- Force re-query (refresh): re-extracts even if outputs exist.

What the tool does:
- Retrieves the active Study Area polygon for the requested project from the Project_Study_Area service (EndDate IS NULL).
- Queries the Standard Connection Reference Table (a feature service) for records with ProjectType = 'all'.
- For each reference record it:
  - Buffers the study area as specified,
  - Connects to the referenced service (FeatureServer / MapServer),
  - Subsets features by spatial relationship and extracts them into the project's default geodatabase under a safe, sanitized name,
  - Optionally applies styling from a LYRX layer file,
  - Adds extracted layers to (or creates) a "Site Details Map" and applies conventions (spatial reference, basemap).
- Produces console messages with success/failure/skipped lists for each reference record.

---

## Configuration

- LAYERFILE_PATH (module-level constant):
  - Default: r"G:\Shared drives\99.3 GIS Admin\Production\Layer Files\AEP - Study Area.lyrx"
  - Update this path to your standard symbology layer file if stored elsewhere. If the file is missing the toolbox will still run but styling will be skipped or fallback will be attempted.

- Feature service URLs:
  - The script includes hard-coded service URLs (Project Study Area service and Standard Connection Reference Table). If you host your own services, update these URLs inside the toolbox script accordingly:
    - Project Study Area: configured as `target_layer_url`
    - Reference table: configured as `reference_table_url`

- Authentication:
  - The toolbox uses arcpy.GetSigninToken() to include the current ArcGIS Pro sign-in token in REST requests where helpful. Ensure you are signed into ArcGIS Online or your Portal in ArcGIS Pro.

---

## Optional helpers

- pct_report helper:
  - The script attempts to import `pct_report.create_pct_report`. If present, the toolbox will call out to this helper to create additional reports. This helper is optional—absence will not block the toolbox.

---

## Tips, behaviour & known issues

- Always run the toolbox inside an ArcGIS Pro project with an active map / layout to allow map updates and programmatic zoom/adding layers.
- Geocoding:
  - Address suggestions are provided from the Esri World Geocode service. Results depend on the quality of input and network availability.
- Cadastre selection:
  - The script first tries a strict CONTAINS selection to get the parcel. If that fails it does a small (2 m) geodesic buffer and uses INTERSECT as a fallback.
- Service append/archive:
  - Before appending a new study area, the script attempts to find active records (EndDate IS NULL) for the same project number and sets EndDate to now to archive them. If the remote service rejects updates the script will warn but will still try to append the new record.
- Styling:
  - The script attempts a "style swap" (import LYRX and update connectionProperties). If that fails it falls back to ApplySymbologyFromLayer. Some ArcGIS Pro runtimes or layer objects may not support all APIs — fallbacks exist but may produce warnings.
- Temporary data:
  - The toolbox creates many in-memory and default geodatabase temporary feature classes (prefixes like `temp_`, `tmp_extract_`, `temp_dissolved_`). The script attempts to clean them up at the end. In rare cases file locks or permission issues may leave temp data — check your geodatabase for any leftover FCs beginning with those prefixes.
- Timeouts and network:
  - REST requests have timeouts (set in the script). Large or slow services may require increased timeout values; edit the `urllib.request.urlopen(..., timeout=...)` calls if needed.

---

## Debugging

- The toolbox uses arcpy.AddMessage / AddWarning / AddError extensively. Review geoprocessing messages in ArcGIS Pro for details of what happened during a run.
- For tracebacks, the script logs the Python traceback using traceback.format_exc() in warnings or errors.
- If a particular referenced service fails to produce a layer, examine the Reference Table entry (URL, style path) and test the REST endpoint directly in a browser.

---

## Development notes

- The code attempts to be robust across multiple ArcGIS Pro API variations (different layer object capabilities) with numerous try/except blocks and sensible fallbacks.
- Feature class names saved into the file geodatabase are sanitized to be geodatabase-safe (non-alphanumeric replaced, leading digits prefixed, truncated).
- The script uses geodesic area calculations for accuracy when computing area and buffers.
- If you make changes and want to run the toolbox from source, replace the toolbox item in ArcGIS Pro with the modified `.pyt` or update the toolbox in-place.

---

## Contributing / Issues

- Please open issues on the repository with:
  - A clear description of the problem
  - Relevant ArcGIS Pro version and Python environment
  - Geoprocessing messages or tracebacks (full text)
- Pull requests are welcome. Keep changes confined to clear features or bug-fixes and include test instructions.

---

## License and authorship

- Author / maintainer: TheKillerKangaroo (GitHub)
- License: (Please add a LICENSE file or indicate preferred license here.)

---
