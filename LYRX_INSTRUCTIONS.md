# LYRX (Layer file) instructions & best-practices

This file explains how to prepare and use a LYRX symbology file with the AEP Project Framework toolbox.

Purpose
- The toolbox attempts a "style swap" for imported layers: import the LYRX into the map and update its connection properties to point at the layer/data source that was just added. This preserves server connection and advanced symbology where possible.
- If the swap fails, the toolbox falls back to ApplySymbologyFromLayer.

Preparing a LYRX file
1. In ArcGIS Pro, create or style a layer that matches the visual conventions for the dataset (colours, labels, renderer, scale ranges).
2. If possible, add to the layer a connection that matches your target data source:
   - Prefer adding the layer using the same service type (Feature Service / Map Service) you intend to style so the LYRX contains sensible connectionProperties.
3. When saving:
   - Right-click the styled layer → Save As Layer File... → save as a `.lyrx`.
   - Keep the LYRX file to a shared network location or inside a deployment path accessible to all project users.

Naming & inner-layer considerations
- If your LYRX contains a Group Layer, the toolbox will try to pick the first non-group child that contains connectionProperties.
- The toolbox attempts to detect a "preferred inner layer name" when reading the LYRX. If your LYRX contains multiple layers, ensure the primary styled layer has a distinct name (e.g., "AEP - Study Area").
- Avoid embedding absolute machine-local paths inside the LYRX (ArcGIS Pro stores relative connection info where possible). Use network-shared paths where team members need consistent access.

Where to place the LYRX
- Set the module-level constant LAYERFILE_PATH at the top of `AEP_Project_Framework_v4.0.pyt` to the full path of your LYRX file.
  - Example: `LAYERFILE_PATH = r"\\fileserver\gis\lyrfiles\AEP - Study Area.lyrx"`
- If LAYERFILE_PATH is missing or points to a non-existent file, the toolbox will continue but styling will be skipped or fall back to ApplySymbologyFromLayer where supported.

Troubleshooting
- If style swap doesn't apply:
  - Confirm the LYRX contains a layer with connectionProperties (i.e., was saved from a service-connected layer).
  - Try using a simpler LYRX with a single layer.
  - Check ArcGIS Pro warnings/messages (ApplySymbologyFromLayer may fail for complex renderers).
- If symbology applies but layers appear broken:
  - The toolbox uses updateConnectionProperties which requires compatible connection types. If the LYRX was saved from a different service type (MapServer vs FeatureServer), update might fail and ApplySymbologyFromLayer will be used instead.
- If you cannot share a LYRX on a network path, include a copy inside your project folder and point LAYERFILE_PATH to that copy.

Advanced
- If you want to maintain different styles per-layer referenced by the Standard Connection Reference Table, store LYRX files and reference their paths in the Reference Table entries (this toolbox supports per-record "Style" values that point to a LYRX).
- For reproducible environments, track LYRX files in your repository (if license/organization policy allows) or in a central shared folder with documented path.