# Create Site By Property — Tool Documentation

Creates a standardized subject site polygon from an NSW address and writes it to the feature service (Step 1). This ArcGIS Python toolbox (.pyt) wraps the refactored script `CreateSiteByProperty.py` and exposes the tool in ArcGIS as a GUI tool. The toolbox calls `CreateSiteByProperty.run_create_site(...)` and reports progress via `arcpy.AddMessage` / `arcpy.AddError`.

> NOTE: This toolbox implements Step 1 only. The parameter to "Run Step 2 automatically after Step 1" is present in the GUI but is NOT IMPLEMENTED by this toolbox — run Step 2 using the separate "Step 2 - Add Standard Project Layers" tool provided in the project.

## Repository / Location
Toolbox file:
- CreateSite/CreateSiteByProperty.pyt (this file is the ArcGIS toolbox wrapper)

Script (required to be colocated with the toolbox):
- CreateSite/CreateSiteByProperty.py (the refactored implementation; must be in the same folder as the .pyt for import)

If the toolbox cannot import the script you will see an error: "Could not import CreateSiteByProperty.py. Ensure the script is in the same folder as this toolbox."

## Prerequisites
- ArcGIS with Python + arcpy available (ArcGIS Desktop or ArcGIS Pro). The toolbox is an ArcGIS Python toolbox and requires the arcpy library to run.
- Place `CreateSiteByProperty.py` in the same folder as `CreateSiteByProperty.pyt`.
- Network access to any external geocoding / web services used by the underlying script (if applicable).
- Appropriate privileges to write to the target feature service.

## How to add and run the tool in ArcGIS
1. In ArcGIS Pro / ArcMap add the toolbox:
   - Right-click the Catalog > Toolboxes > Add Toolbox...
   - Browse to the folder containing `CreateSiteByProperty.pyt` and add it.
2. Open (double-click) the "Create Site By Property" tool.
3. Fill in parameters (see below) and click OK / Run.

When the tool runs it will call `CreateSiteByProperty.run_create_site(...)` and write messages and errors into the tool's geoprocessing messages pane.

## Parameters (GUI)
These parameters are defined in the toolbox and are presented in the ArcGIS tool dialog.

- Address Search (Type and press Tab)
  - Name: `search_text`
  - Type: GPString (text)
  - Required: Yes
  - Behavior: Free-text search field used to request address suggestions. Type at least 4 characters and press Tab (or otherwise alter the field) to trigger suggestion lookup.

- Select Exact Address
  - Name: `site_address`
  - Type: GPString (dropdown with value list)
  - Required: Yes
  - Behavior: Populated by address suggestions returned by the implementation (if available). You must select an address from this dropdown; the tool will show an error if this remains empty.

- Project Number
  - Name: `project_number`
  - Type: GPString
  - Required: Yes
  - Validation: Must be numeric and up to 5 digits. The toolbox provides a sample default `"6666"`.

- Project Name
  - Name: `project_name`
  - Type: GPString
  - Required: Yes
  - Validation: Maximum 150 characters. The toolbox provides a sample default `"Devil's Pinch"`.

- Overwrite existing project data (Step 2)
  - Name: `overwrite_existing`
  - Type: GPBoolean
  - Optional: Yes
  - Purpose: Passed to the underlying workflow to indicate Step 2 behaviour (if Step 2 is executed separately). Not used to bypass Step 1 validations.

- Run Step 2 automatically after Step 1 (NOT IMPLEMENTED)
  - Name: `run_step2_automatically`
  - Type: GPBoolean
  - Optional: Yes
  - Note: This option is present in the UI for future convenience but currently has no effect. Use the separate Step 2 tool to add standard project layers.

- Force re-query even if output exists (refresh)
  - Name: `force_requery`
  - Type: GPBoolean
  - Optional: Yes
  - Purpose: Forces the script to re-run queries even if an output is already present (useful for refreshing cached results).

## How address suggestions work (UI behaviour)
- If the underlying script module exposes a `_get_suggestions` function, the toolbox will try to call it to populate the `Select Exact Address` dropdown as the user types in `Address Search`.
- Suggestions are attempted only when the search field is altered and contains more than 3 characters.
- If the module also provides `_get_token` for authentication, the toolbox will attempt to acquire a token first. Failures in acquiring suggestions are silently ignored by the toolbox (so the UI still works even if suggestions are unavailable).

## Calling the tool programmatically
You can run the encapsulated logic programmatically by importing the implementation script directly (useful for automation outside ArcGIS GUI). Example usage (conceptual — adapt to the actual implementation signature in CreateSiteByProperty.py):

```python
# Example (from a Python environment that has arcpy and the script on sys.path)
import CreateSiteByProperty as create_site_mod

site_address = "123 Example St, SUBURB NSW 2000"
project_number = "01234"
project_name = "Sample Project"
res = create_site_mod.run_create_site(site_address,
                                      project_number,
                                      project_name,
                                      overwrite_flag=False,
                                      run_step2_flag=False,
                                      force_requery=False)
# res is expected to be a dict-like result; the toolbox checks res.get("success")
print(res)
```

The toolbox expects `run_create_site(...)` to return a mapping with at least a `"success"` boolean key. Messages and errors are also posted to ArcGIS geoprocessing messages by the toolbox and implementation.

## Output & Results
- Primary output: a standardized subject site polygon saved back to a feature service or project layer (as implemented in `CreateSiteByProperty.py`).
- The toolbox will post status messages using `arcpy.AddMessage(...)` and will post errors using `arcpy.AddError(...)`.
- If `run_create_site()` returns a result where `"success"` is falsy, the toolbox will add an error: "CreateSiteByProperty reported failure. Check messages above."

## Validation rules enforced in the toolbox
- `Select Exact Address` must be non-empty.
- `Project Number` must be numeric and <=5 digits.
- `Project Name` must be <=150 characters.

These rules are enforced via `updateMessages()` in the .pyt toolbox and will prevent the tool running until fixed.

## Troubleshooting
- "Could not import CreateSiteByProperty.py" — ensure `CreateSiteByProperty.py` is present in the same directory as the .pyt and that it has no import errors. Check the Python console or geoprocessing messages for a traceback.
- If address suggestions do not appear, it may be because:
  - The implementation does not include `_get_suggestions`.
  - A `_get_suggestions` call failed (network, authentication, or the module's token provider).
  - You typed fewer than 4 characters (the toolbox requires >3 before requesting suggestions).
- If the tool fails with arcpy errors, ensure you have a valid ArcGIS license and write access to the destination feature service.
- Check the geoprocessing messages pane for detailed errors and any traceback printed by the toolbox.

## Notes for developers
- The toolbox inserts its directory on sys.path so `CreateSiteByProperty.py` can be imported when colocated.
- The toolbox suppresses suggestion lookup failures (so the GUI remains usable even if suggestion service is unavailable).
- Keep the .pyt and implementation .py together in the same folder when distributing the toolbox.
- When modifying the underlying script, maintain the `run_create_site(...)` return contract (a dict with at least `"success"` boolean) to preserve toolbox behaviour.

## Contact / Contributing
- For issues with the toolbox or implementation, open an issue in the repository where the toolbox lives (link to the project repository).
- When contributing enhancements (for example: auto-run Step 2), make sure to update both the toolbox and the underlying script and keep users informed in this documentation.
