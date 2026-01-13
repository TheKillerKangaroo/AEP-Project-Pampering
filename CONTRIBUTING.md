# Contributing

Thanks for contributing! This document describes the preferred workflow, coding conventions and how to submit useful issues and pull requests.

How to contribute
- Issues
  - Search existing issues before creating a new one.
  - Use the repository issue template (see .github/ISSUE_TEMPLATE.md).
  - Provide ArcGIS Pro version, Python/runtime, geoprocessing messages and any relevant service URLs if possible.

- Pull Requests
  - Fork the repository and create a feature branch: `feature/<short-desc>` or a bugfix branch: `fix/<short-desc>`.
  - Keep changes focused and small. One logical change per PR helps review.
  - Include a clear description, motivation, and testing steps.
  - Add messages and example inputs used to verify the change.
  - If your change affects configuration (service URLs, layer file paths), include a short section in the PR description describing how to update them.

Coding style & testing
- This toolbox runs inside ArcGIS Pro; test your changes in a live ArcGIS Pro project.
- Use arcpy logging patterns consistent with the existing script:
  - arcpy.AddMessage, arcpy.AddWarning, arcpy.AddError for user-facing messages.
- Keep extensive try/except blocks for robustness when interacting with network services.
- Sanitize any file / feature class names written to geodatabases using the existing _sanitize_fc_name helper.

Configuration changes
- If you change any hard-coded URLs or LAYERFILE_PATH, document the change in the README and in LYRX_INSTRUCTIONS.md where relevant.

Security & data privacy
- Do not commit credentials or tokens to the repository.
- When reporting issues that include service endpoints or sample data, ensure you’re permitted to share that data publicly. If not, redact or provide sanitized test data.

License
- Ensure your contributions are compatible with the repository license (add or update LICENSE if necessary).

Thanks again — your contributions improve the toolbox for everyone!