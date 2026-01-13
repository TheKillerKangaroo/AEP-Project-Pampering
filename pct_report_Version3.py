# PCT report helper - reusable function to create PCT_Report table
# Place this file next to your toolbox code and import with:
# from pct_report import create_pct_report
#
# The function requires arcpy to be available (run inside ArcGIS Pro / python environment).

import os
import arcpy
import traceback
from datetime import datetime
from typing import Optional


def _get_field_by_candidates(field_list, candidates):
    for c in candidates:
        for f in field_list:
            if f.lower() == c.lower():
                return f
    return None


def create_pct_report(pct_fc: str, default_gdb: str, site_area_m2: float, pct_table_name: str = "PCT_Report") -> Optional[str]:
    """
    Create a PCT_Report table in default_gdb summarising the PCT layer pct_fc.

    Parameters:
    - pct_fc: path to the PCT feature class (local FGDB path or layer)
    - default_gdb: path to the default geodatabase where PCT_Report will be created
    - site_area_m2: total study area in square metres (used to compute SiteCoveragePct if needed)
    - pct_table_name: name for the report table (default "PCT_Report")

    Returns: full path to the created report table on success, or None on failure.
    Logs messages via arcpy.AddMessage / AddWarning / AddError.
    """
    try:
        if not pct_fc:
            arcpy.AddWarning("create_pct_report: pct_fc not provided.")
            return None
        if not default_gdb:
            arcpy.AddWarning("create_pct_report: default_gdb not provided.")
            return None

        arcpy.AddMessage(f"Creating PCT report from '{pct_fc}' -> '{os.path.join(default_gdb, pct_table_name)}'")

        # Ensure needed fields exist
        if not arcpy.ListFields(pct_fc, "area_m"):
            try:
                arcpy.management.AddField(pct_fc, "area_m", "DOUBLE")
            except Exception as e:
                arcpy.AddWarning(f"Could not add field 'area_m' to {pct_fc}: {e}")

        if not arcpy.ListFields(pct_fc, "SiteCoveragePct"):
            try:
                arcpy.management.AddField(pct_fc, "SiteCoveragePct", "DOUBLE")
            except Exception as e:
                arcpy.AddWarning(f"Could not add field 'SiteCoveragePct' to {pct_fc}: {e}")

        # Calculate area_m and SiteCoveragePct using geodesic area
        arcpy.AddMessage("  - Calculating area_m and SiteCoveragePct for each PCT feature...")
        with arcpy.da.UpdateCursor(pct_fc, ["SHAPE@", "area_m", "SiteCoveragePct"]) as uc:
            for row in uc:
                geom = row[0]
                a_m = geom.getArea("GEODESIC", "SQUAREMETERS")
                row[1] = a_m
                pct = (100.0 * a_m / site_area_m2) if site_area_m2 > 0 else 0.0
                row[2] = round(pct, 1)
                uc.updateRow(row)

        # Gather fields and find PCTID / PCTName
        pct_fields = [f.name for f in arcpy.ListFields(pct_fc)]
        pctid_field = _get_field_by_candidates(pct_fields, ["PCTID", "pctid", "PCT_ID"])
        pctname_field = _get_field_by_candidates(pct_fields, ["PCTName", "pctname", "PCT_Name", "PCTNAME"])

        if not pctid_field or not pctname_field:
            arcpy.AddWarning("Could not find PCTID and/or PCTName fields in PCT layer; cannot create PCT_Report.")
            return None

        # Summarize
        arcpy.AddMessage("  - Summarizing PCT entries...")
        summary = {}
        with arcpy.da.SearchCursor(pct_fc, [pctid_field, pctname_field, "area_m", "SiteCoveragePct"]) as sc:
            for r in sc:
                key = (r[0], r[1])
                if key not in summary:
                    summary[key] = {"area_m": 0.0, "sitecov": 0.0}
                summary[key]["area_m"] += (r[2] or 0.0)
                summary[key]["sitecov"] += (r[3] or 0.0)

        # Create table in default_gdb
        pct_table = os.path.join(default_gdb, pct_table_name)
        try:
            if arcpy.Exists(pct_table):
                arcpy.management.Delete(pct_table)
            arcpy.management.CreateTable(default_gdb, pct_table_name)
            arcpy.management.AddField(pct_table, "PCTID", "TEXT", field_length=50)
            arcpy.management.AddField(pct_table, "PCTName", "TEXT", field_length=255)
            arcpy.management.AddField(pct_table, "Sum_area_m", "DOUBLE")
            arcpy.management.AddField(pct_table, "Sum_SiteCoveragePct", "DOUBLE")

            with arcpy.da.InsertCursor(pct_table, ["PCTID", "PCTName", "Sum_area_m", "Sum_SiteCoveragePct"]) as ins:
                for (pid, pname), vals in summary.items():
                    ins.insertRow([str(pid), str(pname), vals["area_m"], round(vals["sitecov"], 1)])

            arcpy.AddMessage(f"  ✓ PCT_Report created: {pct_table}")
            return pct_table
        except Exception as e:
            arcpy.AddError(f"Failed to create PCT_Report: {e}\n{traceback.format_exc()}")
            return None

    except Exception as e_outer:
        arcpy.AddError(f"Unexpected error in create_pct_report: {e_outer}\n{traceback.format_exc()}")
        return None


# Optional CLI usage: run from ArcGIS Python if called as script
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: pct_report.py <pct_fc> <default_gdb> <site_area_m2> [pct_table_name]")
    else:
        pct_fc = sys.argv[1]
        default_gdb = sys.argv[2]
        try:
            site_area_m2 = float(sys.argv[3])
        except Exception:
            site_area_m2 = 0.0
        table_name = sys.argv[4] if len(sys.argv) > 4 else "PCT_Report"
        create_pct_report(pct_fc, default_gdb, site_area_m2, pct_table_name=table_name)