# ArcGIS Pro Project Framework Workflow

## Overview
This document describes the automated workflow for creating standardized ArcGIS Pro projects for environmental assessment in New South Wales, Australia.  The `TargetSite_Toolbox.pyt` Python Toolbox automates the extraction of spatial data from NSW government services and sets up a complete project workspace.

---

## Workflow Steps

### **1. Query and Extract Parcels**

**Input Required:**
- Lot/Plan IDs (comma-separated format:  `1//DP90465, 3//DP171105`)

**Process:**
1. Parses and validates the input Lot/Plan ID list
2. Constructs a WHERE clause for the REST API query
3. Queries the **NSW Land Parcel Property Theme FeatureServer (Layer 8)**
   - URL: `https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer/8`
4. Downloads matching parcel geometries as JSON
5. Converts JSON to temporary feature class in scratch geodatabase
6. Returns all parcels matching the provided Lot/Plan IDs

**Output:**
- Temporary feature class containing selected parcels

---

### **2. Create Subject Site Boundary**

**Process:**
1. Repairs geometry of downloaded parcels using `RepairGeometry`
2. Dissolves all selected parcels into a single unified polygon using `Dissolve`
   - Dissolve field: `None` (all features combined)
   - Multi-part:  `MULTI_PART`
   - Unsplit lines: `DISSOLVE_LINES`
3. Simplifies the boundary using `CopyFeatures`
4. Creates the final "Subject Site" feature class

**Output:**
- Single polygon feature class representing the project site boundary
- Temporary output (will be deleted after project creation)

---

### **3. Set Up Project Structure**

**Input Required:**
- Project Number (7 characters max, e.g., `6666`)
- Project Description (100 characters max, e.g., `Devils Pinch`)
- Template Project Folder Path (e.g., `C:\ArcGIS Templates\AEP_STD_Template`)
- Overwrite Existing Project (Boolean)

**Process:**
1. Checks if project folder already exists at `C:\ArcGIS Projects\AEP{ProjectNumber}`
2. If overwrite is enabled and folder exists: 
   - Deletes existing project folder using `shutil.rmtree()`
3.  Copies template project folder to new location using `shutil.copytree()`
4. Renames `.aprx` file to `AEP{ProjectNumber}_{ProjectDescription}.aprx`
5. Renames geodatabase folder to `AEP{ProjectNumber}. gdb`
6. Sets the new geodatabase as the project's default geodatabase

**Output:**
- New project folder structure based on template
- Renamed project file and geodatabase

---

### **4. Create Feature Datasets**

**Spatial Reference:**
- GDA2020 / NSW Lambert (EPSG: 9473)

**Feature Datasets Created:**
1. **AdminBoundaries** - For administrative boundary data
2. **Cadastre** - For property/parcel data
3. **Flora** - For vegetation/plant community data
4. **Fauna** - For wildlife data (empty, for later use)
5. **Arborculture** - For tree survey data (empty)
6. **Aquatic** - For water features (empty)
7. **SiteFeatures** - For site boundaries, buffers, and site-specific features
8. **Planning** - For zoning and planning data
9. **Bushfire** - For bushfire risk data

**Output:**
- 9 standardized feature datasets in project geodatabase

---

### **5. Copy Site Data to Project**

**Input (Optional):**
- WAPWeeds Feature Class (optional weeds/invasive species layer)

**Process:**
1. Copies Subject Site boundary to `SiteFeatures` dataset as `Subject_Site_{ProjectNumber}`
2. Adds and calculates project attribute fields:
   - `Project_No` (TEXT, 7 chars) - Project number
   - `Project_Desc` (TEXT, 100 chars) - Project description
   - `Area_ha` (DOUBLE) - Site area in hectares (calculated from `! shape.area@hectares! `)
   - `Large_Site` (TEXT, 3 chars) - "Yes" if area ≥ 50 ha, otherwise "No"
3. Creates 2000m buffer around site using `Buffer` tool
   - Buffer distance: 2000 Meters
   - Dissolve option: ALL
   - Saved as `TargetSite_Buffer_2000m` in `SiteFeatures` dataset
4. If WAPWeeds layer provided: 
   - Validates feature class name
   - Copies to `SiteFeatures` dataset
   - Adds layer to project map

**Output:**
- Subject Site feature class with project attributes
- 2000m buffer feature class
- Optional weeds layer

---

### **6. Populate Administrative Boundaries**

**Function:** `populate_admin_boundaries_from_service()`

**Data Source:**
- NSW Administrative Boundaries Theme FeatureServer
- URL: `https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Administrative_Boundaries_Theme/FeatureServer`

**Process:**
1. Queries FeatureServer metadata to retrieve list of all available layers
2. For each layer in the service:
   - Validates layer name using `arcpy.ValidateTableName()`
   - Names output as `T{layer_id}_{layer_name}`
   - Clips layer to 2000m buffer using `Clip` tool
   - Adds `Extract_date` field (DATE type)
   - Populates `Extract_date` with current date using `datetime.date.today()`
   - Saves to `AdminBoundaries` dataset
3. Skips layers that already exist
4. Reports success count

**Output:**
- All administrative boundary layers clipped to buffer extent
- Each layer includes extraction date for version tracking

---

### **7. Populate Cadastre Data**

**Function:** `populate_cadastre_from_service()`

**Data Source:**
- NSW Land Parcel Property Theme FeatureServer
- URL: `https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer`

**Process:**
1. Queries FeatureServer metadata to retrieve list of all available layers
2. For each layer in the service: 
   - Validates layer name using `arcpy.ValidateTableName()`
   - Names output as `T{layer_id}_{layer_name}`
   - Clips layer to 2000m buffer using `Clip` tool
   - Adds `Extract_date` field (DATE type)
   - Populates `Extract_date` with current date
   - Saves to `Cadastre` dataset
3. Skips layers that already exist
4. Reports success count

**Typical Layers Included:**
- Property boundaries
- Lot boundaries
- Address points
- Road centerlines
- Other cadastral features

**Output:**
- All cadastral layers clipped to buffer extent
- Each layer includes extraction date

---

### **8. Populate Flora/Vegetation Data**

**Function:** `populate_flora_from_service()`

**Data Source:**
- NSW Vegetation MapServer (SVTM_NSW_Extant_PCT)
- URL: `https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/VIS/SVTM_NSW_Extant_PCT/MapServer`

**Target Layer:**
- **Layer 3 only**:  Plant Community Type (PCT)

**Clip Extent:**
- Subject Site boundary (NOT the 2000m buffer - more precise)

**Process:**
1. Queries MapServer metadata to identify Layer 3
2. Clips Layer 3 (Plant Community Type) to Subject Site boundary
   - Saves to temporary location in scratch geodatabase
3. **Dissolves** features by vegetation attributes:
   - `PCTID` - Plant Community Type ID
   - `PCTName` - Plant Community Type Name
   - `vegForm` - Vegetation formation
   - `vegClass` - Vegetation class
   - `form_PCT` - Formation and PCT combined
   - `labels` - Display labels
   - Multi-part:  MULTI_PART
4. Calculates area attributes:
   - `Area_sqm` (DOUBLE) - Area in square metres (`!shape.area@squaremeters!`)
   - `Area_ha` (DOUBLE) - Area in hectares (`!shape.area@hectares!`)
   - `Area_Pct` (DOUBLE) - Percentage of total site area
     - Formula: `(feature_area_sqm / total_site_area_sqm) * 100`
5. Adds `Extract_date` field and populates with current date
6. Saves as `Plant_Community_Type_{ProjectNumber}` in `Flora` dataset
7. Deletes temporary clip feature class

**Output:**
- Dissolved vegetation layer with area statistics
- Enables vegetation impact assessment and reporting

---

### **9. Populate Planning/Zoning Data**

**Function:** `populate_planning_layers_from_service()`

**Data Source:**
- NSW Planning Principal Planning Layers MapServer
- URL: `https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/Planning/Principal_Planning_Layers/MapServer`

**Target Layer:**
- **Layer 11**:  LZN (Land Zoning)

**Clip Extent:**
- 2000m buffer (provides context beyond site boundary)

**Process:**
1. Validates output feature class name (`LZN`)
2. Clips Layer 11 (Land Zoning) to 2000m buffer using `Clip` tool
3. Adds `Extract_date` field (DATE type)
4. Populates `Extract_date` with current date
5. Saves as `LZN` in `Planning` dataset
6. Skips if layer already exists

**Output:**
- Land zoning layer showing zoning designations within buffer area
- Essential for planning compliance assessment

---

### **10. Populate Bushfire Data**

**Function:** `populate_bushfire_layer_from_service()`

**Data Source:**
- NSW BushFire Prone Land FeatureServer
- URL: `https://portal.spatial.nsw.gov. au/server/rest/services/Hosted/NSW_BushFire_Prone_Land/FeatureServer/0`

**Clip Extent:**
- 2000m buffer

**Process:**
1. Validates output feature class name (`Bushfire_Prone_Land`)
2. Clips Layer 0 (Bushfire Prone Land) to 2000m buffer using `Clip` tool
3. Adds `Extract_date` field (DATE type)
4. Populates `Extract_date` with current date
5. Saves as `Bushfire_Prone_Land` in `Bushfire` dataset
6. Skips if layer already exists

**Output:**
- Bushfire prone land classification layer
- Critical for bushfire risk assessment and APZ (Asset Protection Zone) planning

---

### **11. Add Layers to Map**

**Target Map:**
- "Map 1 - Site Details" (must exist in template project)

**Process:**
1. Opens ArcGIS Pro project using `arcpy.mp.ArcGISProject()`
2. Identifies target map by name
3. Adds layers to map using `addDataFromPath()`:
   - Subject Site boundary (`Subject_Site_{ProjectNumber}`)
   - 2000m buffer (`TargetSite_Buffer_2000m`)
   - WAPWeeds layer (if copied)
4. Sets map extent to Subject Site boundary: 
   - Retrieves extent using `arcpy.Describe().extent`
   - Updates default camera extent
5. Saves project using `project.save()`

**Output:**
- Map view configured with site layers
- Map extent zoomed to site boundary

---

### **12. Cleanup and Finalization**

**Cleanup Process:**
1. Deletes temporary feature classes: 
   - `TempParcels` (from scratch geodatabase)
   - `DissolvedParcels` (from scratch geodatabase)
   - `Clipped_PCT_{ProjectNumber}_TEMP` (from scratch geodatabase)
2. Deletes temporary JSON file (`temp_results.json`)
3. Deletes intermediate output feature class (original query result)
4. Saves ArcGIS Pro project file

**Auto-Launch Process:**
1. Locates ArcGIS Pro executable at `C:\Program Files\ArcGIS\Pro\bin\ArcGISPro.exe`
2. Launches ArcGIS Pro with new project using `subprocess. Popen()`
3. Opens project in new process (non-blocking)

**Output:**
- Clean workspace with no temporary files
- ArcGIS Pro project automatically opened and ready to use

---

## Data Summary by Feature Dataset

### **AdminBoundaries**
- **Spatial Extent:** 2000m buffer
- **Content:** All layers from NSW Administrative Boundaries Theme
- **Examples:** Local government areas, suburbs, electorates, regions

### **Cadastre**
- **Spatial Extent:** 2000m buffer
- **Content:** All layers from NSW Land Parcel Property Theme
- **Examples:** Properties, lots, addresses, roads

### **Flora**
- **Spatial Extent:** Subject Site boundary (precise)
- **Content:** Plant Community Type layer (dissolved)
- **Attributes:** PCTID, PCTName, vegForm, vegClass, Area_ha, Area_sqm, Area_Pct

### **Fauna**
- **Spatial Extent:** N/A
- **Content:** Empty (for user to populate)
- **Purpose:** Wildlife survey data storage

### **Arborculture**
- **Spatial Extent:** N/A
- **Content:** Empty (for user to populate)
- **Purpose:** Tree survey and arborist report data

### **Aquatic**
- **Spatial Extent:** N/A
- **Content:** Empty (for user to populate)
- **Purpose:** Waterway, wetland, and aquatic ecology data

### **SiteFeatures**
- **Spatial Extent:** Subject Site + 2000m buffer
- **Content:** 
  - Subject Site boundary with project metadata
  - 2000m buffer
  - Optional WAPWeeds layer
- **Attributes:** Project_No, Project_Desc, Area_ha, Large_Site

### **Planning**
- **Spatial Extent:** 2000m buffer
- **Content:** LZN (Land Zoning) layer
- **Purpose:** Planning controls and zoning designation analysis

### **Bushfire**
- **Spatial Extent:** 2000m buffer
- **Content:** Bushfire Prone Land classification
- **Purpose:** Bushfire risk assessment

---

## Key Features

### **Automation Benefits**
- Eliminates manual data downloading from multiple government portals
- Standardizes project structure across all projects
- Reduces project setup time from hours/days to minutes
- Ensures consistent spatial reference (GDA2020 NSW Lambert)
- Automatic date stamping for data version control

### **Error Handling**
- REST API connection timeout handling (15-30 seconds)
- Geometry repair for downloaded features
- Feature class name validation to prevent illegal characters
- Checks for existing data to avoid duplication
- Detailed error messages with "Russian comrade" humor theme

### **Spatial Reference**
- **EPSG Code:** 9473
- **Name:** GDA2020 / NSW Lambert
- **Type:** Projected Coordinate System
- **Datum:** Geocentric Datum of Australia 2020
- **Projection:** Lambert Conformal Conic
- **Appropriate for:** NSW regional/state-wide analysis

### **Overwrite Protection**
- Optional deletion of existing project folders
- Default:  Overwrite disabled (safe mode)
- Manual confirmation required via checkbox parameter
- Uses `shutil.rmtree()` for complete folder removal

### **Data Currency**
- All extracted layers include `Extract_date` field
- Date populated using `datetime.date.today()`
- Enables tracking of data vintage
- Important for regulatory compliance and reporting

---

## Tool Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| Lot/Plan ID List | String | Yes | `1//DP90465,3//DP171105,4//DP171105,1//DP1133689` | Comma-separated list of lot/plan identifiers in format `{lot}//DP{plan}` |
| Output Target Site Feature Class | Feature Class | Yes | *(auto-generated)* | Temporary output location for site boundary (deleted after project creation) |
| Project Number | String | Yes | `6666` | 7-character project identifier (e.g., `AEP-001`, `6666`) |
| Project Description | String | Yes | `Devils Pinch` | 100-character project description (used in project file name) |
| Template Project Folder Path | Folder | Yes | *(none)* | Path to template project folder (e.g., `C:\ArcGIS Templates\AEP_STD_Template`) |
| Optional Weeds Feature Class | Feature Class | No | *(none)* | Path to WAPWeeds or other invasive species feature class |
| Overwrite Existing Project Folder | Boolean | No | `False` | Enable deletion of existing project folder at destination path |

---

## Output Structure

```
C:\ArcGIS Projects\
└── AEP{ProjectNumber}\
    ├── AEP{ProjectNumber}_{ProjectDescription}.aprx   # ArcGIS Pro project file
    ├── AEP{ProjectNumber}. gdb\                        # File geodatabase
    │   ├── AdminBoundaries\                           # Feature dataset
    │   │   ├── T0_LayerName                          # Clipped admin layers (all)
    │   │   ├── T1_LayerName
    │   │   └── ... 
    │   ├── Cadastre\                                  # Feature dataset
    │   │   ├── T8_LOT                                # Clipped cadastre layers (all)
    │   │   ├── T9_ADDRESS
    │   │   └── ... 
    │   ├── Flora\                                     # Feature dataset
    │   │   └── Plant_Community_Type_{ProjectNumber}  # Dissolved vegetation
    │   ├── Fauna\                                     # Feature dataset (empty)
    │   ├── Arborculture\                              # Feature dataset (empty)
    │   ├── Aquatic\                                   # Feature dataset (empty)
    │   ├── SiteFeatures\                              # Feature dataset
    │   │   ├── Subject_Site_{ProjectNumber}          # Site boundary with attributes
    │   │   ├── TargetSite_Buffer_2000m               # 2000m buffer
    │   │   └── [WAPWeeds layer]                      # Optional weeds layer
    │   ├── Planning\                                  # Feature dataset
    │   │   └── LZN                                   # Land zoning layer
    │   └── Bushfire\                                  # Feature dataset
    │       └── Bushfire_Prone_Land                   # Bushfire risk layer
    └── [Other template files/folders]                 # From template project
```

---

## Data Sources

### **NSW Spatial Services**
- **Cadastre:** NSW Land Parcel Property Theme FeatureServer
  - `https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer`
- **Admin Boundaries:** NSW Administrative Boundaries Theme FeatureServer
  - `https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Administrative_Boundaries_Theme/FeatureServer`
- **Bushfire:** NSW BushFire Prone Land FeatureServer
  - `https://portal.spatial.nsw.gov.au/server/rest/services/Hosted/NSW_BushFire_Prone_Land/FeatureServer/0`

### **NSW Department of Planning and Environment**
- **Vegetation:** SVTM NSW Extant PCT MapServer
  - `https://mapprod3.environment.nsw. gov.au/arcgis/rest/services/VIS/SVTM_NSW_Extant_PCT/MapServer`
- **Planning:** Principal Planning Layers MapServer
  - `https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/Planning/Principal_Planning_Layers/MapServer`

---

## Error Handling and Warnings

### **Common Warning Messages**
- `"Project folder already exists.  Overwrite not selected."` - Enable overwrite parameter
- `"Query returned zero features."` - Check Lot/Plan IDs are correct
- `"Template folder not found."` - Verify template path exists
- `"Feature Dataset not found."` - Template may be missing required datasets
- `"Layer already exists.  Skipping."` - Re-running tool with existing data

### **Critical Error Conditions**
- REST API connection failure (timeout, network issues)
- Invalid Lot/Plan ID format
- Missing template folder
- Insufficient disk space
- ArcGIS Pro licensing issues
- Write permission errors in output location

---

## Best Practices

### **Before Running**
1. Verify template project exists and contains required maps
2. Ensure sufficient disk space (estimate ~500MB per project minimum)
3. Check Lot/Plan IDs are correctly formatted
4. Confirm network connectivity to NSW government services
5. Close any existing project files with the same name

### **Template Requirements**
- Must contain a map named "Map 1 - Site Details"
- Should include predefined symbology for common layer types
- Should include standard layouts and layout elements
- File geodatabase should exist (will be renamed)

### **Data Management**
- Regular template updates to maintain consistency
- Archive old projects before overwriting
- Document data extraction dates for regulatory compliance
- Backup projects before making major modifications

### **Performance Optimization**
- Run during off-peak hours for faster REST API responses
- Use local template folders (not network paths)
- Close unnecessary applications to free memory
- Process one project at a time for large/complex sites

---

## Use Cases

### **Environmental Impact Assessments**
- Site vegetation analysis
- Threatened species habitat assessment
- Bushfire risk evaluation
- Planning compliance checking

### **Development Applications**
- Planning proposal support
- Zoning verification
- Cadastral context analysis
- Flora and fauna impact statements

### **Site Investigations**
- Baseline environmental studies
- Preliminary site assessments
- Due diligence investigations
- Desktop ecological studies

---

## Limitations

- **NSW-specific:** Data sources are NSW government services only
- **Internet required:** Cannot run offline (REST API dependent)
- **Template dependent:** Requires properly configured template project
- **Windows paths:** Hardcoded paths assume Windows OS (`C:\` drive)
- **ArcGIS Pro only:** Not compatible with ArcMap
- **Single site:** Processes one project at a time (not batch)
- **Data currency:** Downloaded data reflects current state of government services

---

## Future Enhancement Opportunities

1. **Batch Processing:** Support multiple projects in single execution
2. **Custom Data Sources:** Configurable service URLs
3. **Cross-platform:** Support macOS/Linux paths
4. **Offline Mode:** Pre-downloaded data packages
5. **Additional Layers:** Heritage, contamination, flooding, etc.
6. **Report Generation:** Automated PDF reports with statistics
7. **Email Notifications:** Project completion alerts
8. **Cloud Storage:** Azure/AWS integration for project storage
9. **Web Interface:** Browser-based parameter input
10. **Quality Assurance:** Automated data validation and integrity checks

---

## Support and Maintenance

### **Script Location**
- Filename: `TargetSite_Toolbox.pyt`
- Type: Python Toolbox for ArcGIS Pro
- Language: Python 3.x (ArcGIS Pro Python environment)

### **Dependencies**
- ArcGIS Pro (with Spatial Analyst license recommended)
- Python packages:
  - `arcpy` (included with ArcGIS Pro)
  - `requests` (for REST API calls)
  - `json` (for JSON parsing)
  - `os`, `sys` (file operations)
  - `datetime` (date stamping)
  - `shutil` (folder operations)
  - `subprocess` (Pro launching)

### **Maintenance Tasks**
- Monitor NSW government service URL changes
- Update EPSG codes if datum changes
- Verify template compatibility with new ArcGIS Pro versions
- Test after NSW government service updates
- Review and update field calculations as needed

---

## Glossary

- **PCT:** Plant Community Type - NSW vegetation classification system
- **LZN:** Land Zoning - Planning zone designations
- **DP:** Deposited Plan - Survey plan type in NSW cadastre
- **GDA2020:** Geocentric Datum of Australia 2020 - Current national datum
- **EPSG: 9473:** GDA2020 NSW Lambert projected coordinate system code
- **WAPWeeds:** Weed Action Plan weeds database
- **APZ:** Asset Protection Zone - Bushfire protection buffer
- **REST API:** Representational State Transfer Application Programming Interface
- **FeatureServer:** ArcGIS server type supporting feature editing and querying
- **MapServer:** ArcGIS server type supporting map rendering and querying (read-only)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| Current | 2026-01-08 | - Added AdminBoundaries dataset population<br>- Added Bushfire dataset population<br>- Added WAPWeeds optional layer support<br>- Fixed syntax errors in field calculations<br>- Enhanced error handling |

---

## License and Attribution

This tool accesses public data from: 
- **NSW Spatial Services** (Department of Customer Service)
- **NSW Department of Planning and Environment**

Users must comply with NSW government data licensing terms and attribution requirements.

---

*End of Workflow Documentation*
