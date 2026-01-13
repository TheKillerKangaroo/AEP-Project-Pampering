# PCT_Analysis.py
# Helper module to run PCT (Project Connection Table) style extraction/clip workflow.
# Intended to be imported by AEP_Project_Framework_v4.0.pyt
# Requires arcpy (ArcGIS Pro).

import arcpy
import os
import time
import uuid
import json
import urllib.request
import urllib.parse
import traceback
import re

# Default reference table URL (same service used by Step 2)
DEFAULT_REFERENCE_TABLE_URL = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15"

def _sanitize_fc_name(name, max_len=63):
    if not name:
        return "layer"
    s = re.sub(r'[^0-9A-Za-z_]', '_', str(name))
    s = re.sub(r'_{2,}', '_', s)
    s = s.strip('_')
    if not s:
        s = "layer"
    if re.match(r'^\d', s):
        s = f"f_{s}"
    if len(s) > max_len:
        s = s[:max_len]
    return s

def _get_token_from_aprx():
    try:
        info = arcpy.GetSigninToken()
        return info.get("token") if info else None
    except Exception:
        return None

def query_pct_reference_records(reference_table_url=None, token=None):
    """
    Query the reference table for ProjectType = 'pct'.
    Returns list of reference features (each is dictionary with attributes).
    """
    url = reference_table_url or DEFAULT_REFERENCE_TABLE_URL
    params = {"where": "ProjectType='pct'", "outFields": "*", "f": "json", "orderByFields": "SortOrder ASC"}
    if token:
        params["token"] = token
    qurl = f"{url}/query?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(qurl, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        return data.get("features", [])
    except Exception as e:
        arcpy.AddWarning(f"PCT reference table query failed: {e}")
        return []

def _ensure_feature_dataset(gdb, dataset_name, spatial_reference=None):
    """
    Ensure a feature dataset exists in the given gdb. Returns path to dataset (gdb/dataset).
    If dataset_name is None/empty, returns gdb (features will be created at root).
    """
    if not dataset_name:
        return gdb
    fd_path = os.path.join(gdb, dataset_name)
    try:
        if arcpy.Exists(fd_path):
            return fd_path
        # create dataset, require spatial reference; fallback to GDA2020 (8058) or 4326
        sr = None
        if spatial_reference:
            sr = spatial_reference
        else:
            try:
                sr = arcpy.SpatialReference(4326)
            except:
                sr = None
        arcpy.management.CreateFeatureDataset(gdb, dataset_name, sr)
        return fd_path
    except Exception as e:
        arcpy.AddWarning(f"Could not create feature dataset '{dataset_name}' in {gdb}: {e}")
        return gdb

def run_pct_analysis(aprx, study_area_fc, project_number,
                     output_gdb=None,
                     overwrite_flag=False,
                     force_requery=False,
                     reference_table_url=None,
                     token=None):
    """
    Main routine to run PCT extraction.
    - aprx: arcpy.mp.ArcGISProject("CURRENT") instance (used to add layers if desired)
    - study_area_fc: path to study area feature (can be in_memory or path)
    - project_number: the project number for naming and logging
    - output_gdb: geodatabase path to write outputs. If None, aprx.defaultGeodatabase is used.
    - overwrite_flag: if True, existing outputs will be replaced
    - force_requery: if True, forces extraction even if output exists
    - reference_table_url: optional override for the reference table REST endpoint
    - token: optional authentication token for REST queries

    Returns: list of dicts describing outputs produced and errors for diagnostics.
    """
    results = []
    try:
        if not token:
            token = _get_token_from_aprx() if aprx is not None else _get_token_from_aprx()

        default_gdb = output_gdb or (aprx.defaultGeodatabase if aprx is not None else None)
        if not default_gdb:
            arcpy.AddError("No output geodatabase specified and no aprx default geodatabase available.")
            return results

        arcpy.AddMessage("=" * 60)
        arcpy.AddMessage("STEP 3 - PCT ANALYSIS")
        arcpy.AddMessage("=" * 60)

        # compute a single geodesic area for logging
        try:
            site_area_m2 = 0.0
            with arcpy.da.SearchCursor(study_area_fc, ["SHAPE@"]) as sc:
                for r in sc:
                    site_area_m2 = r[0].getArea("GEODESIC", "SQUAREMETERS")
                    break
            arcpy.AddMessage(f"  ✓ Study area size: {site_area_m2:.2f} m²")
        except Exception:
            arcpy.AddWarning("Could not compute study area size for PCT summary.")

        # fetch reference records for PCT
        records = query_pct_reference_records(reference_table_url=reference_table_url, token=token)
        arcpy.AddMessage(f"  ✓ Found {len(records)} PCT reference record(s).")

        # prepare site_map if aprx and map available
        site_map = None
        try:
            if aprx:
                site_map = aprx.activeMap
        except Exception:
            site_map = None

        # helper to access attributes case-insensitively
        def _get_attr_ci(attrs, key):
            for k, v in attrs.items():
                if k.lower() == key.lower():
                    return v
            return None

        for idx, feat in enumerate(records, start=1):
            rec = {"index": idx}
            try:
                attrs = feat.get("attributes", {})
                service_url = _get_attr_ci(attrs, "URL") or _get_attr_ci(attrs, "Url") or _get_attr_ci(attrs, "url")
                site_buffer = _get_attr_ci(attrs, "SiteBuffer") or _get_attr_ci(attrs, "sitebuffer") or 0
                buffer_action = _get_attr_ci(attrs, "BufferAction") or _get_attr_ci(attrs, "bufferaction") or "INTERSECT"
                feature_dataset_name = _get_attr_ci(attrs, "FeatureDatasetName") or _get_attr_ci(attrs, "FeatureDataset") or ""
                short_name = _get_attr_ci(attrs, "ShortName") or _get_attr_ci(attrs, "Shortname") or f"pct_{idx}"
                style_file = _get_attr_ci(attrs, "Style") or _get_attr_ci(attrs, "LayerFile") or _get_attr_ci(attrs, "lyrx")

                safe_short = _sanitize_fc_name(short_name)

                rec.update({"short_name": short_name, "safe_short": safe_short, "service_url": service_url})

                if not service_url:
                    arcpy.AddWarning(f"  - Reference record '{short_name}' has no URL; skipping.")
                    rec["skipped"] = True
                    results.append(rec)
                    continue

                arcpy.AddMessage(f"Processing PCT record {idx}: '{short_name}' (buffer={site_buffer}) URL='{service_url}'")

                # Build output paths
                fd_path = _ensure_feature_dataset(default_gdb, feature_dataset_name, spatial_reference=None)
                out_fc_final = os.path.join(fd_path, safe_short)

                # Quick existence check
                if arcpy.Exists(out_fc_final) and not overwrite_flag and not force_requery:
                    arcpy.AddMessage(f"  - Output {out_fc_final} already exists. Overwrite disabled and force re-query not set -> SKIP")
                    rec["skipped"] = True
                    results.append(rec)
                    continue

                # Build buffer (per-record) if requested
                try:
                    distance_m = float(site_buffer) if site_buffer not in (None, '') else 0.0
                except:
                    distance_m = 0.0

                buffer_fc = None
                # If distance_m > 0, create buffer in memory; else buffer_fc is study_area_fc (used for selection/clip)
                if distance_m > 0:
                    buffer_fc = os.path.join("in_memory", f"pct_buf_{safe_short}_{uuid.uuid4().hex[:6]}")
                    try:
                        if arcpy.Exists(buffer_fc):
                            arcpy.management.Delete(buffer_fc)
                        arcpy.analysis.Buffer(study_area_fc, buffer_fc, f"{distance_m} Meters", method="GEODESIC")
                        arcpy.AddMessage(f"  • Created buffer {buffer_fc} ({distance_m} m).")
                    except Exception as e:
                        arcpy.AddWarning(f"  - Could not create buffer for '{short_name}': {e}")
                        buffer_fc = study_area_fc
                else:
                    buffer_fc = study_area_fc

                # Try making a temporary layer from the service
                temp_layer_name = f"tmp_pct_layer_{safe_short}_{int(time.time())}"
                made_layer = False
                try:
                    # prefer MakeFeatureLayer (same approach as Step 2)
                    arcpy.management.MakeFeatureLayer(service_url, temp_layer_name)
                    made_layer = True
                except Exception as e:
                    arcpy.AddWarning(f"  - Could not make feature layer for '{service_url}': {e}\n{traceback.format_exc()}")

                # Attempt spatial selection
                selected_count = 0
                selected_oids = []
                try:
                    if made_layer:
                        arcpy.management.SelectLayerByLocation(temp_layer_name, buffer_action, buffer_fc)
                        selected_count = int(arcpy.management.GetCount(temp_layer_name).getOutput(0))
                        arcpy.AddMessage(f"  • {selected_count} feature(s) intersect buffer for '{short_name}'.")
                        if selected_count > 0:
                            # Determine OID field name
                            desc = arcpy.Describe(temp_layer_name)
                            oid_field = getattr(desc, "oidFieldName", "OBJECTID")
                            with arcpy.da.SearchCursor(temp_layer_name, [oid_field]) as sc:
                                for r in sc:
                                    selected_oids.append(int(r[0]))
                    else:
                        arcpy.AddWarning(f"  - Layer creation failed for '{service_url}' — skipping selection.")
                except Exception as sel_e:
                    arcpy.AddWarning(f"  - Selection by location failed for '{short_name}': {sel_e}\n{traceback.format_exc()}")

                # If nothing selected, skip
                if not selected_oids:
                    arcpy.AddMessage(f"  - No intersecting features found for '{short_name}'. Skipping.")
                    # cleanup layer if exists
                    try:
                        if made_layer:
                            arcpy.management.Delete(temp_layer_name)
                    except:
                        pass
                    rec["skipped"] = True
                    results.append(rec)
                    continue

                # Prepare final output: create or replace as needed by copying first piece, then append subsequent pieces
                created_any = False
                piece_count = 0
                for oid in selected_oids:
                    piece_count += 1
                    piece_info = {"oid": oid}
                    try:
                        # Select single feature by object id on the temporary layer
                        where_clause = f"{desc.oidFieldName} = {oid}"
                        try:
                            arcpy.management.SelectLayerByAttribute(temp_layer_name, "NEW_SELECTION", where_clause)
                        except Exception:
                            # Sometimes server requires quoting or different field name; fallback using a search cursor to copy directly
                            arcpy.AddWarning(f"  - Select by attribute failed for OID {oid} on '{short_name}'; will attempt to use REST/geometry fallback.")
                            # fallback: try REST query to get geometry/attributes and create in-memory fc (not implemented here)
                            raise

                        # copy selected single feature to in_memory
                        temp_piece = os.path.join("in_memory", f"pct_piece_{safe_short}_{oid}_{uuid.uuid4().hex[:4]}")
                        if arcpy.Exists(temp_piece):
                            try: arcpy.management.Delete(temp_piece)
                            except: pass
                        arcpy.management.CopyFeatures(temp_layer_name, temp_piece)
                        piece_info["temp_piece"] = temp_piece

                        # optionally clip the piece to buffer_fc/study area (only if clip is required):
                        # We assume clip is required for PCT outputs; if you want to rely on a field to control clip,
                        # you can change logic to check an attribute (e.g. 'ClipToSite').
                        clip_needed = True
                        clipped_piece = temp_piece
                        if clip_needed and buffer_fc and buffer_fc != temp_piece:
                            clipped_piece = os.path.join("in_memory", f"pct_clipped_{safe_short}_{oid}_{uuid.uuid4().hex[:4]}")
                            try:
                                if arcpy.Exists(clipped_piece):
                                    try: arcpy.management.Delete(clipped_piece)
                                    except: pass
                                arcpy.analysis.Clip(temp_piece, buffer_fc, clipped_piece)
                                piece_info["clipped_piece"] = clipped_piece
                            except Exception as clip_e:
                                # If clip fails, fall back to using the original piece
                                arcpy.AddWarning(f"  - Clip failed for '{short_name}' oid {oid}: {clip_e}")
                                clipped_piece = temp_piece

                        # write/append to final output
                        if not created_any:
                            # create final feature class
                            try:
                                if arcpy.Exists(out_fc_final):
                                    if overwrite_flag:
                                        try:
                                            arcpy.management.Delete(out_fc_final)
                                        except Exception:
                                            pass
                                if not arcpy.Exists(out_fc_final):
                                    arcpy.management.CopyFeatures(clipped_piece, out_fc_final)
                                else:
                                    # exists and we are appending
                                    arcpy.management.Append(clipped_piece, out_fc_final, "NO_TEST")
                            except Exception as create_e:
                                arcpy.AddWarning(f"  - Could not create initial output {out_fc_final}: {create_e}\n{traceback.format_exc()}")
                                raise
                            created_any = True
                        else:
                            try:
                                arcpy.management.Append(clipped_piece, out_fc_final, "NO_TEST")
                            except Exception as append_e:
                                arcpy.AddWarning(f"  - Could not append piece oid {oid} to {out_fc_final}: {append_e}")
                                raise

                        # cleanup piece(s)
                        try:
                            if arcpy.Exists(temp_piece):
                                arcpy.management.Delete(temp_piece)
                            if "clipped_piece" in piece_info and piece_info["clipped_piece"] and arcpy.Exists(piece_info["clipped_piece"]):
                                arcpy.management.Delete(piece_info["clipped_piece"])
                        except Exception:
                            pass

                        arcpy.AddMessage(f"    • Processed oid {oid} for '{short_name}'.")
                        piece_info["status"] = "ok"
                    except Exception as piece_ex:
                        arcpy.AddWarning(f"    - Failed processing oid {oid} for '{short_name}': {piece_ex}\n{traceback.format_exc()}")
                        piece_info["status"] = "failed"
                    # record piece info (not too verbose)
                    if "pieces" not in rec:
                        rec["pieces"] = []
                    rec["pieces"].append(piece_info)

                # cleanup temp service layer
                try:
                    if made_layer:
                        arcpy.management.Delete(temp_layer_name)
                except:
                    pass

                # Add to map if aprx + site_map and user wants (we don't force)
                try:
                    if aprx and site_map and created_any:
                        try:
                            added = site_map.addDataFromPath(out_fc_final)
                            arcpy.AddMessage(f"  ✓ Added output '{out_fc_final}' to map.")
                        except Exception:
                            pass
                except Exception:
                    pass

                rec.update({
                    "out_fc": out_fc_final,
                    "created": created_any,
                    "pieces_processed": piece_count,
                    "selected_count": len(selected_oids)
                })
                results.append(rec)

            except Exception as rec_e:
                arcpy.AddWarning(f"Error processing PCT record index {idx}: {rec_e}\n{traceback.format_exc()}")
                rec["error"] = str(rec_e)
                results.append(rec)
                # continue processing next records
                continue

        arcpy.AddMessage("\nSTEP 3 PCT ANALYSIS COMPLETE.")
        return results

    except Exception as e:
        arcpy.AddError(f"STEP 3 error: {e}\n{traceback.format_exc()}")
        return results


# If you want a lightweight CLI-like entry when invoking the script directly (rare inside Pro),
# you can add a __main__ that extracts environment vars or arguments. Keep minimal.
if __name__ == "__main__":
    arcpy.AddMessage("PCT_Analysis.py executed directly — intended to be imported and called by toolbox.")