# CreateSiteByProperty.py
# Standalone script containing the refactored "Step 1 - Create Subject Site" logic
# Designed to be imported by a Python toolbox (CreateSiteByProperty.pyt) or executed directly.
#
# NOTE: This script intentionally focuses on Step 1 only. It does not automatically run Step 2.
# To run Step 2, use the existing "Step 2 - Add Standard Project Layers" tool in your toolbox.
#
# Dependencies: arcpy, Python standard libs (os, json, urllib, datetime, time, re, uuid, traceback)

import arcpy
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime
import time
import re
import uuid
import traceback

# Global path used for styling swap — keep as in original code
LAYERFILE_PATH = r"G:\Shared drives\99.3 GIS Admin\Production\Layer Files\AEP - Study Area.lyrx"

# Optional external helper left as import attempt for parity; not required for Step 1.
try:
    from pct_report import create_pct_report
except Exception:
    create_pct_report = None


def build_project_defq(project_number, layer=None):
    """
    Copied/ported helper to build a WHERE clause for project_number + EndDate IS NULL.
    Works the same as original: attempts to inspect 'layer' to detect numeric field types,
    otherwise falls back to value-based detection.
    """
    if project_number is None:
        return "EndDate IS NULL"

    pn = str(project_number).strip()

    def quoted(val):
        return "'" + val.replace("'", "''") + "'"

    if layer is not None:
        try:
            for f in arcpy.ListFields(layer):
                if f.name.lower() in ("project_number", "projectnumber", "project_num", "projectnum"):
                    ftype = getattr(f, "type", "").lower()
                    if ftype in ("smallinteger", "integer", "single", "double", "oid", "long"):
                        try:
                            if pn.isdigit():
                                return f"project_number = {int(pn)} AND EndDate IS NULL"
                            fv = float(pn)
                            if fv.is_integer():
                                return f"project_number = {int(fv)} AND EndDate IS NULL"
                        except Exception:
                            return f"project_number = {quoted(pn)} AND EndDate IS NULL"
                    else:
                        return f"project_number = {quoted(pn)} AND EndDate IS NULL"
        except Exception:
            pass

    if pn.isdigit():
        return f"project_number = {int(pn)} AND EndDate IS NULL"
    try:
        f = float(pn)
        if f.is_integer():
            return f"project_number = {int(f)} AND EndDate IS NULL"
    except Exception:
        pass

    return f"project_number = {quoted(pn)} AND EndDate IS NULL"


def _get_token():
    try:
        info = arcpy.GetSigninToken()
        return info.get("token") if info else None
    except Exception:
        return None


def _get_suggestions(text, token):
    base = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/suggest"
    params = {"text": text, "f": "json", "maxSuggestions": 10, "countryCode": "AUS"}
    if token:
        params["token"] = token

    try:
        url = f"{base}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        if "suggestions" in data:
            return [s["text"] for s in data["suggestions"]]
        return []
    except Exception:
        return []


def _normalize_added(added):
    """
    Normalise addDataFromPath return and pick a usable layer object (same approach as original).
    Returns (top_object, child_layer_or_none, parent_object_or_none).
    """
    top = added
    try:
        if isinstance(added, (list, tuple)):
            if len(added) > 0:
                top = added[0]
            else:
                top = None
    except Exception:
        top = added

    if top is None:
        return (None, None, None)

    parent = top
    child = top
    try:
        if getattr(top, "isGroupLayer", False):
            try:
                children = top.listLayers()
                if children:
                    for c in children:
                        if getattr(c, "connectionProperties", None) is not None or getattr(c, "isGroupLayer", False) is False:
                            child = c
                            break
                    if child is None and len(children) > 0:
                        child = children[0]
            except Exception:
                child = None
    except Exception:
        pass

    return (top, child or top, parent if parent is not child else None)


def _apply_style_swap(site_map, data_layer, style_path, display_name=None, set_defq=None):
    """
    Attempt style swap / symbology application (ported from original). Returns final_layer or None.
    """
    final_layer = data_layer
    preferred_layer_name = None
    try:
        if os.path.exists(style_path):
            try:
                lf = arcpy.mp.LayerFile(style_path)
                lf_layers = lf.listLayers()
                for l in lf_layers:
                    lname = getattr(l, "name", None)
                    if getattr(l, "connectionProperties", None) is not None or not getattr(l, "isGroupLayer", False):
                        preferred_layer_name = lname
                        break
            except Exception:
                preferred_layer_name = None
    except Exception:
        preferred_layer_name = None

    try:
        added = site_map.addDataFromPath(style_path)
    except Exception as e:
        arcpy.AddWarning(f"  - Could not import style '{style_path}': {e}")
        return None

    top, style_layer, parent = _normalize_added(added)
    try:
        if preferred_layer_name and top and getattr(top, "listLayers", None):
            try:
                for c in top.listLayers():
                    if getattr(c, "name", "") == preferred_layer_name:
                        style_layer = c
                        break
            except Exception:
                pass
    except Exception:
        pass

    if style_layer is None:
        arcpy.AddWarning(f"  - Imported style produced no usable layer object: {style_path}")
        try:
            if top and top is not data_layer:
                site_map.removeLayer(top)
        except Exception:
            pass
        return None

    try:
        conn_props = data_layer.connectionProperties
    except Exception:
        conn_props = None
    try:
        def_query = data_layer.definitionQuery if data_layer.supports("DEFINITIONQUERY") else None
    except Exception:
        def_query = None

    update_ok = False
    if conn_props:
        try:
            update_func = getattr(style_layer, "updateConnectionProperties", None)
            style_conn_props = getattr(style_layer, "connectionProperties", None)
            if callable(update_func) and style_conn_props is not None:
                try:
                    update_func(style_conn_props, conn_props)
                    update_ok = True
                except AttributeError as ae:
                    arcpy.AddMessage(f"  - updateConnectionProperties not supported by this layer object: {ae}")
                    try:
                        arcpy.management.ApplySymbologyFromLayer(style_layer, style_path)
                        update_ok = True
                        arcpy.AddMessage("  • Applied symbology to imported style layer via ApplySymbologyFromLayer (fallback).")
                    except Exception as e2:
                        arcpy.AddWarning(f"  - ApplySymbologyFromLayer fallback failed: {e2}")
                except Exception as e:
                    arcpy.AddWarning(f"  - updateConnectionProperties failed: {e}")
                    try:
                        arcpy.management.ApplySymbologyFromLayer(style_layer, style_path)
                        update_ok = True
                        arcpy.AddMessage("  • Applied symbology to imported style layer via ApplySymbologyFromLayer (fallback).")
                    except Exception as e2:
                        arcpy.AddWarning(f"  - ApplySymbologyFromLayer fallback failed: {e2}")
            else:
                arcpy.AddMessage("  - updateConnectionProperties not available on imported style; attempting ApplySymbologyFromLayer fallback.")
                try:
                    arcpy.management.ApplySymbologyFromLayer(style_layer, style_path)
                    update_ok = True
                    arcpy.AddMessage(f"  • Applied symbology to imported style layer via ApplySymbologyFromLayer as workaround.")
                except Exception as e2:
                    arcpy.AddWarning(f"  - ApplySymbologyFromLayer fallback also failed: {e2}\n{traceback.format_exc()}")
        except Exception as e:
            arcpy.AddWarning(f"  - Error while attempting connection update/fallback for '{style_path}': {e}")

    try:
        if set_defq and style_layer.supports("DEFINITIONQUERY"):
            style_layer.definitionQuery = set_defq
        elif def_query and style_layer.supports("DEFINITIONQUERY"):
            style_layer.definitionQuery = def_query
    except Exception:
        pass

    try:
        if display_name:
            style_layer.name = display_name
    except Exception:
        pass

    try:
        site_map.removeLayer(data_layer)
    except Exception:
        try:
            data_layer.visible = False
        except:
            pass

    try:
        if parent and parent is not style_layer:
            try:
                site_map.removeLayer(parent)
            except Exception:
                pass
    except Exception:
        pass

    final_layer = style_layer
    return final_layer


def _cleanup_duplicates(site_map, final_layer, display_name, preexisting_names=None):
    """
    Remove or hide duplicate layers with same display name that existed before this run.
    """
    try:
        final_name = getattr(final_layer, "name", display_name)

        for lyr in list(site_map.listLayers()):
            try:
                if getattr(lyr, "name", "") == final_name:
                    try:
                        if getattr(lyr, "longName", "") == getattr(final_layer, "longName", ""):
                            continue
                    except Exception:
                        if lyr is final_layer:
                            continue

                if getattr(lyr, "name", "") != display_name:
                    continue

                if preexisting_names is not None:
                    if display_name not in preexisting_names:
                        continue
                    try:
                        site_map.removeLayer(lyr)
                        arcpy.AddMessage(f"  • Removed pre-existing duplicate layer '{display_name}'.")
                    except Exception:
                        try:
                            lyr.visible = False
                        except Exception:
                            pass
                else:
                    try:
                        lyr.visible = False
                        arcpy.AddMessage(f"  • Hid duplicate layer '{display_name}' (conservative fallback).")
                    except Exception:
                        try:
                            site_map.removeLayer(lyr)
                            arcpy.AddMessage(f"  • Removed duplicate layer '{display_name}' (fallback).")
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass


def run_create_site(site_address, project_number, project_name,
                    overwrite_flag=False, run_step2_flag=False, force_requery=False):
    """
    Main entrypoint for Step 1 processing.

    Parameters:
        site_address (str): the selected address (single-line string)
        project_number (str)
        project_name (str)
        overwrite_flag (bool): preserved for parity; not used by standalone script here
        run_step2_flag (bool): If True, the script will try to hand off to Step 2 only if a callable
                               step2 runner is discoverable (not implemented by default).
        force_requery (bool): unused in this simplified separation but accepted for API parity.

    Returns:
        dict with summary keys: success (bool), study_area (path or None), appended (bool), archived_count (int)
    """
    target_layer_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"

    arcpy.AddMessage("=" * 60)
    arcpy.AddMessage("STEP 1 - CREATE SUBJECT SITE (refactored standalone)")
    arcpy.AddMessage("=" * 60)

    archived_count = 0
    appended_success = False
    matched_address = ""
    area_ha = 0.0

    created_temp_paths = set()
    removed_temp_paths = []
    failed_temp_deletes = []

    run_uuid = str(uuid.uuid4())[:8]

    result = {"success": False, "study_area": None, "appended": False, "archived_count": 0}
    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        default_gdb = aprx.defaultGeodatabase
        prior_workspace = None
        try:
            prior_workspace = arcpy.env.workspace
            arcpy.env.workspace = default_gdb
        except Exception:
            pass

        arcpy.env.workspace = default_gdb

        # 1. Geocode
        token = _get_token()
        base_url = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"

        params = {
            'SingleLine': site_address,
            'f': 'json',
            'outSR': '4326',
            'maxLocations': 1,
            'countryCode': 'AUS'
        }
        if token:
            params['token'] = token

        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode())

        if not data.get('candidates'):
            arcpy.AddError(f"Could not locate coordinate for address: {site_address}")
            return result

        candidate = data['candidates'][0]
        matched_address = candidate['address']
        loc = candidate['location']

        geocoded_point = arcpy.PointGeometry(arcpy.Point(loc['x'], loc['y']), arcpy.SpatialReference(4326))
        temp_geocoded = os.path.join("in_memory", f"geocoded_point_{run_uuid}")
        arcpy.management.CopyFeatures(geocoded_point, temp_geocoded)
        created_temp_paths.add(temp_geocoded)

        arcpy.AddMessage(f"Located at: {loc['x']:.5f}, {loc['y']:.5f}")

        # 2. Select property polygon (Cadastre)
        property_service_url = "https://portal.spatial.nsw.gov.au/server/rest/services/NSW_Land_Parcel_Property_Theme/FeatureServer/12"

        temp_property_layer = f"temp_property_layer_{run_uuid}"
        arcpy.management.MakeFeatureLayer(property_service_url, temp_property_layer)

        arcpy.AddMessage("Selecting property parcel...")
        arcpy.management.SelectLayerByLocation(temp_property_layer, "CONTAINS", temp_geocoded)
        property_count = int(arcpy.management.GetCount(temp_property_layer).getOutput(0))

        if property_count == 0:
            arcpy.AddMessage("  - No parcel selected with CONTAINS; trying INTERSECT with a small buffer around the geocoded point as a fallback...")

            try:
                desc = arcpy.Describe(temp_property_layer)
                layer_sr = getattr(desc, "spatialReference", None)

                pt_in = os.path.join("in_memory", f"temp_geocode_copy_{run_uuid}")
                if arcpy.Exists(pt_in):
                    try:
                        arcpy.management.Delete(pt_in)
                    except:
                        pass
                arcpy.management.CopyFeatures(temp_geocoded, pt_in)
                created_temp_paths.add(pt_in)

                proj_pt = pt_in
                if layer_sr and getattr(layer_sr, "factoryCode", None) and layer_sr.factoryCode != 4326:
                    proj_pt = os.path.join("in_memory", f"temp_geocode_proj_{run_uuid}")
                    try:
                        if arcpy.Exists(proj_pt):
                            try:
                                arcpy.management.Delete(proj_pt)
                            except:
                                pass
                        arcpy.management.Project(pt_in, proj_pt, layer_sr)
                    except Exception:
                        proj_pt = pt_in
                    created_temp_paths.add(proj_pt)

                buf_fc = os.path.join("in_memory", f"temp_geocode_buf_{run_uuid}")
                if arcpy.Exists(buf_fc):
                    try:
                        arcpy.management.Delete(buf_fc)
                    except:
                        pass
                arcpy.analysis.Buffer(proj_pt, buf_fc, "2 Meters", method="GEODESIC")
                created_temp_paths.add(buf_fc)

                arcpy.management.SelectLayerByLocation(temp_property_layer, "INTERSECT", buf_fc)
                property_count = int(arcpy.management.GetCount(temp_property_layer).getOutput(0))

                try:
                    arcpy.management.Delete(pt_in)
                except:
                    pass
                try:
                    arcpy.management.Delete(proj_pt)
                except:
                    pass
                try:
                    arcpy.management.Delete(buf_fc)
                except:
                    pass

                if property_count == 0:
                    arcpy.AddError("No property polygon found at this location (NSW Cadastre) after fallback attempt.")
                    return result
                else:
                    arcpy.AddMessage(f"  ✓ Found {property_count} parcel(s) using buffer+INTERSECT fallback.")

            except Exception as e:
                arcpy.AddWarning(f"  - Buffer/INTERSECT fallback failed: {e}")
                arcpy.AddError("No property polygon found at this location (NSW Cadastre).")
                return result

        # Copy selection to local GDB
        temp_property = os.path.join(default_gdb, f"temp_property_{run_uuid}")
        if arcpy.Exists(temp_property):
            arcpy.management.Delete(temp_property)
        arcpy.management.CopyFeatures(temp_property_layer, temp_property)
        created_temp_paths.add(temp_property)

        try:
            arcpy.management.Delete(temp_property_layer)
        except:
            pass
        try:
            arcpy.management.Delete(temp_geocoded)
            if temp_geocoded in created_temp_paths:
                created_temp_paths.discard(temp_geocoded)
                removed_temp_paths.append(temp_geocoded)
        except:
            pass

        arcpy.management.RepairGeometry(temp_property, "DELETE_NULL")

        # Handle multi-polygon properties (dissolve)
        if property_count > 1:
            dissolved_mem = os.path.join("in_memory", f"temp_dissolved_{run_uuid}")
            dissolved_gdb = os.path.join(default_gdb, f"temp_dissolved_{run_uuid}")
            try:
                if arcpy.Exists(dissolved_mem):
                    try:
                        arcpy.management.Delete(dissolved_mem)
                    except:
                        pass

                arcpy.AddMessage("  • Performing Dissolve in memory to avoid gdb locks...")
                arcpy.management.Dissolve(temp_property, dissolved_mem, multi_part="MULTI_PART")

                if arcpy.Exists(dissolved_gdb):
                    try:
                        arcpy.management.Delete(dissolved_gdb)
                    except:
                        pass
                arcpy.management.CopyFeatures(dissolved_mem, dissolved_gdb)
                created_temp_paths.add(dissolved_gdb)
                working_fc = dissolved_gdb

                try:
                    if arcpy.Exists(dissolved_mem):
                        arcpy.management.Delete(dissolved_mem)
                except:
                    pass

            except arcpy.ExecuteError as ge:
                arcpy.AddWarning(f"Memory Dissolve failed: {ge}\nAttempting alternative dissolve in default geodatabase.")
                try:
                    arcpy.ClearWorkspaceCache_management()
                except:
                    pass

                alt_name = f"temp_dissolved_{int(time.time())}_{run_uuid}"
                alt_dissolved = os.path.join(default_gdb, alt_name)
                try:
                    arcpy.management.Dissolve(temp_property, alt_dissolved, multi_part="MULTI_PART")
                    working_fc = alt_dissolved
                    created_temp_paths.add(alt_dissolved)
                except Exception as e2:
                    arcpy.AddError(f"Could not perform Dissolve (tried memory and file gdb): {e2}")
                    raise

        else:
            working_fc = temp_property

        # 3. Add & Calculate Attributes
        arcpy.AddMessage("Preparing attributes...")
        target_fields = [
            ("project_number", "TEXT", 256),
            ("ProjectName", "TEXT", 150),
            ("GeocodedAddress", "TEXT", 255),
            ("SiteArea", "DOUBLE", None),
            ("AreaUnits", "TEXT", 20),
            ("Area_ha", "DOUBLE", None),
            ("Comments", "TEXT", 255),
            # Ensure EndDate exists locally so we can explicitly set it to NULL
            # for the new record written to the feature service.
            ("EndDate", "DATE", None),
        ]

        for fname, ftype, flen in target_fields:
            if not arcpy.ListFields(working_fc, fname):
                if ftype == "TEXT":
                    arcpy.management.AddField(working_fc, fname, ftype, field_length=flen)
                else:
                    arcpy.management.AddField(working_fc, fname, ftype)

        # Include EndDate so we can force it to NULL on the new record.
        with arcpy.da.UpdateCursor(
            working_fc,
            ["SHAPE@", "project_number", "ProjectName", "GeocodedAddress", "SiteArea", "AreaUnits", "Area_ha", "EndDate"],
        ) as cursor:
            for row in cursor:
                area_sqm = row[0].getArea("GEODESIC", "SQUAREMETERS")
                area_ha = area_sqm / 10000.0
                area_units = "hectares" if area_sqm > 10000 else "square meters"

                row[1] = project_number
                row[2] = project_name
                row[3] = matched_address
                row[4] = area_ha if area_units == "hectares" else area_sqm
                row[5] = area_units
                row[6] = area_ha
                # Explicitly clear EndDate so the appended feature is active.
                row[7] = None
                cursor.updateRow(row)

        arcpy.AddMessage(f"  ✓ Site area: {area_ha:.2f} hectares")

        # 4. Archive existing active records on the target feature service
        try:
            arcpy.AddMessage("Checking target feature service for existing active project records (EndDate IS NULL)...")
            temp_target_layer = f"temp_target_layer_{run_uuid}"
            arcpy.management.MakeFeatureLayer(target_layer_url, temp_target_layer)
            where_clause = build_project_defq(project_number, layer=temp_target_layer)
            arcpy.management.SelectLayerByAttribute(temp_target_layer, "NEW_SELECTION", where_clause)
            existing_count = int(arcpy.management.GetCount(temp_target_layer).getOutput(0))
            if existing_count > 0:
                arcpy.AddMessage(f"  - Found {existing_count} active record(s). Archiving by setting EndDate to now.")
                now_dt = datetime.now()
                try:
                    with arcpy.da.UpdateCursor(temp_target_layer, ["EndDate"]) as ucur:
                        for urow in ucur:
                            urow[0] = now_dt
                            ucur.updateRow(urow)
                    arcpy.AddMessage("  ✓ Archived existing record(s) by updating EndDate.")
                    archived_count = existing_count
                except Exception as ue:
                    arcpy.AddWarning(f"  - Could not update EndDate on remote service: {ue}")
            else:
                arcpy.AddMessage("  - No active previous record found; nothing to archive.")
            try:
                arcpy.management.Delete(temp_target_layer)
            except:
                pass
        except Exception as e:
            arcpy.AddWarning(f"Could not check/archive existing records on feature service: {e}")

        # 5. Append to Feature Service
        arcpy.AddMessage("Writing to feature service...")
        try:
            arcpy.management.Append(working_fc, target_layer_url, "NO_TEST")
            appended_success = True
        except Exception as e:
            arcpy.AddError(f"Failed to append to feature service: {e}")
            appended_success = False

        study_area_for_step2 = working_fc
        try:
            if appended_success:
                temp_service_layer_name = f"temp_postappend_service_layer_{run_uuid}"
                try:
                    if arcpy.Exists(temp_service_layer_name):
                        try:
                            arcpy.management.Delete(temp_service_layer_name)
                        except:
                            pass
                    arcpy.management.MakeFeatureLayer(target_layer_url, temp_service_layer_name)
                    where_clause = build_project_defq(project_number, layer=temp_service_layer_name)
                    arcpy.management.SelectLayerByAttribute(temp_service_layer_name, "NEW_SELECTION", where_clause)
                    sel_count = int(arcpy.management.GetCount(temp_service_layer_name).getOutput(0))
                    if sel_count > 0:
                        study_area_mem = os.path.join("in_memory", f"study_area_{project_number}_{run_uuid}")
                        if arcpy.Exists(study_area_mem):
                            try:
                                arcpy.management.Delete(study_area_mem)
                            except:
                                pass
                        arcpy.management.CopyFeatures(temp_service_layer_name, study_area_mem)
                        study_area_for_step2 = study_area_mem
                        created_temp_paths.add(study_area_mem)
                    else:
                        study_area_for_step2 = working_fc
                finally:
                    try:
                        arcpy.management.Delete(temp_service_layer_name)
                    except:
                        pass
        except Exception:
            study_area_for_step2 = working_fc

        # 6. Add to Map (No Zoom)
        try:
            map_obj = aprx.activeMap
            if map_obj:
                try:
                    psa_layer_added = None
                    if appended_success:
                        psa_layer_added = map_obj.addDataFromPath(target_layer_url)
                    else:
                        psa_layer_added = map_obj.addDataFromPath(working_fc)

                    top, child, parent = _normalize_added(psa_layer_added)
                    psa_layer_obj = child or top
                    try:
                        psa_layer_obj.name = f"Project Study Area {project_number}"
                    except:
                        pass

                    final_psa = None
                    if os.path.exists(LAYERFILE_PATH):
                        applied = False
                        try:
                            try:
                                dq_for_psa = build_project_defq(project_number, layer=psa_layer_obj)
                            except Exception:
                                dq_for_psa = build_project_defq(project_number)

                            final = _apply_style_swap(map_obj, psa_layer_obj, LAYERFILE_PATH, display_name=f"Project Study Area {project_number}", set_defq=dq_for_psa)
                            if final is not None:
                                final_psa = final
                                applied = True
                                arcpy.AddMessage("  ✓ Applied standard Study Area symbology to PSA by swapping.")
                            else:
                                try:
                                    arcpy.management.ApplySymbologyFromLayer(psa_layer_obj, LAYERFILE_PATH)
                                    final_psa = psa_layer_obj
                                    applied = True
                                    arcpy.AddMessage("  ✓ Applied standard Study Area symbology using ApplySymbologyFromLayer.")
                                except Exception as e_sym:
                                    arcpy.AddWarning(f"  - Could not apply standard symbology to Project Study Area: {e_sym}\n{traceback.format_exc()}")
                        except Exception as e:
                            arcpy.AddWarning(f"  - Error while attempting to apply style to PSA: {e}\n{traceback.format_exc()}")

                        try:
                            if final_psa and final_psa.supports("DEFINITIONQUERY"):
                                final_psa.definitionQuery = build_project_defq(project_number, layer=final_psa)
                                arcpy.AddMessage("  ✓ Applied definition query to Project Study Area layer.")
                        except Exception:
                            pass
                    else:
                        arcpy.AddWarning("  - PSA layerfile not found; PSA added without standard styling.")
                except Exception as e:
                    arcpy.AddWarning(f"Map update for PSA failed: {e}\n{traceback.format_exc()}")
            else:
                arcpy.AddWarning("No active map to add PSA.")
        except Exception as e:
            arcpy.AddWarning(f"Could not update map: {str(e)}\n{traceback.format_exc()}")

        # Cleanup temporary data
        try:
            arcpy.AddMessage("Cleaning up temporary data created during Step 1...")
            protected = set()
            try:
                if study_area_for_step2:
                    protected.add(os.path.normpath(study_area_for_step2))
            except Exception:
                pass

            for p in list(created_temp_paths):
                try:
                    normp = os.path.normpath(p)
                except Exception:
                    normp = p
                if normp in protected:
                    continue
                try:
                    if arcpy.Exists(p):
                        arcpy.management.Delete(p)
                        removed_temp_paths.append(p)
                    else:
                        removed_temp_paths.append(p)
                except Exception as delerr:
                    failed_temp_deletes.append({"path": p, "error": str(delerr)})
                    continue

            prefixes = ("temp_", "tmp_extract_", "temp_dissolved_", "alt_dissolved_", f"temp_property_{run_uuid}", f"tmp_extract_")
            try:
                prev_ws = arcpy.env.workspace
                arcpy.env.workspace = default_gdb
                fc_list = arcpy.ListFeatureClasses() or []
                for fc in fc_list:
                    try:
                        if any(fc.lower().startswith(pref.lower()) for pref in prefixes):
                            full = os.path.join(default_gdb, fc)
                            if os.path.normpath(full) in protected:
                                continue
                            try:
                                arcpy.management.Delete(full)
                                removed_temp_paths.append(full)
                            except Exception as e_del:
                                failed_temp_deletes.append({"path": full, "error": str(e_del)})
                    except Exception:
                        pass
                tbls = arcpy.ListTables() or []
                for tbl in tbls:
                    try:
                        if any(tbl.lower().startswith(pref.lower()) for pref in prefixes):
                            full = os.path.join(default_gdb, tbl)
                            if os.path.normpath(full) in protected:
                                continue
                            try:
                                arcpy.management.Delete(full)
                                removed_temp_paths.append(full)
                            except Exception as e_del:
                                failed_temp_deletes.append({"path": full, "error": str(e_del)})
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                try:
                    arcpy.env.workspace = prior_workspace
                except Exception:
                    pass

            if removed_temp_paths:
                arcpy.AddMessage("Temporary data removed:")
                for r in removed_temp_paths:
                    arcpy.AddMessage(f"  - {r}")
            if failed_temp_deletes:
                arcpy.AddWarning("Some temporary items could not be deleted (see details):")
                for fi in failed_temp_deletes:
                    arcpy.AddWarning(f"  - {fi.get('path')}: {fi.get('error')}")
        except Exception as e:
            arcpy.AddWarning(f"Cleanup during Step 1 encountered errors: {e}\n{traceback.format_exc()}")

        arcpy.AddMessage("\nSTEP 1 COMPLETE.")

        result["success"] = True
        result["study_area"] = study_area_for_step2
        result["appended"] = appended_success
        result["archived_count"] = archived_count

    except Exception as e:
        arcpy.AddError(f"\n✗ Error: {str(e)}")
        arcpy.AddError(traceback.format_exc())

    return result


def _cli():
    """
    Basic CLI so developers can run the script directly for testing.
    Usage: python CreateSiteByProperty.py "1 Example St, Exampletown NSW" 12345 "Project Name"
    """
    import sys
    if len(sys.argv) < 4:
        print("Usage: CreateSiteByProperty.py <address> <project_number> <project_name>")
        return
    addr = sys.argv[1]
    pn = sys.argv[2]
    pname = sys.argv[3]
    res = run_create_site(addr, pn, pname)
    print("Result:", res)


if __name__ == "__main__":
    _cli()