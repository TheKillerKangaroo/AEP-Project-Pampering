# ArcGIS Pro Project Framework Workflow

## Overview
This document describes the automated workflow for creating standardized ArcGIS Pro projects for environmental assessment in New South Wales, Australia.  

---

## Script 1
## Name: Create Subject Site
## Workflow Steps

**Input Required:**
- Address string
- Project Number
- Project Name

**Process:**
1. The user is asked for the "Site Address". This is a type ahead type input that selects an address from the address attribute in this service: **https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer/12**
2. The polygon for this property recorded is selected and used as the Subject Property
3. Repairs geometry of downloaded property using `RepairGeometry`
2. if the polygon count is > 1 then Dissolves all polugons into a single unified polygon using `Dissolve`
   - Dissolve field: `None` (all features combined)
   - Multi-part:  `MULTI_PART`
4. the user is then asked for the following additional details: Project Number (text up to 5 number characters only), Project Name (text, up to 150 characters)
5. The area of the of the site is then calculated in either square meters or hectares. If the area is greater than 10,000 square meters then the area is stored in hectares else it is in square meters. This is rounded to 3 decimal points and stored in an attribute called "Area", the measure reference, either m² or Ha is stored in an attribute called "Area_measure"
6. The layer is then saved in the project default geodatabase. The layer is named Project_Study_Area.

## Script 2
## Name: Add Standard Project Layers
## Workflow Steps

**Process:**
1. This table: Url	https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15, is queried, using the logged in users credentials, and all records returned WHERE ProjectType = "all". This table is used to determine the layers that are to be queried and results added to the default project geodatabase.
2. For each record returned by this query we need to:
   2.1 buffer the subject site by the distance (in meters) in the SiteBuffer attribute. 
   2.2 connect to the feature layer listed in the attribute URL. The attribute BufferAction will tell us if we have to either use the buffer polygon to either intersect or clip the feature layer records with the buffer to create a subset of records from the layer. if the number of records returned >1 move on to the next step else move on to the next record.
   2.3 The selected records are then copied into the default project database into the Feature Dataset referenced by the FeatureDatasetName attribute (if this does not exist then create it using EPSG: 8058) and it is named as per attribute ShortName.
   2.4 Add additional attributes to the layer saved to the default GDB being: "ExtractDate" (Current date and time) & "ExtractURL" being the URL attribute.
   2.5 Move on to the next record.
4. Create the SiteLotsReport table and save it to the default project gdb. This is created by selecting the following attributes: lotnumber AS "Lot", sectionnumber AS "Section". plannumber AS "Plan", planlotarea AS "PlanLotArea", planlotareaunits as "PlanLotAreaUnits" from the Lots feature class where the records are within the subject site.
5. Create the PCT_Report table. The first step is to calculate the size of each polygon in the SVTM_PCT layer (in m²) and add it to the layer in an attribute called area_m. Then calculate the % of the subject site that this represents (rounded to 1 decimal place) and store that in an attribute called "Site Coverage %). Then the PCT_Report table is created by summing the area_m, Site Coverage % fields grouped by PCTID, PCTName

