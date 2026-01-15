# -*- coding: utf-8 -*-
import arcpy
import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime
import time
import re
import uuid
import traceback
import tempfile

# ------------------------------------------------------------------------------
# LOGIC & HELPER FUNCTIONS
# (Refactored from ImportStdSiteLayers.py)
# ------------------------------------------------------------------------------

# Styling layerfile path
LAYERFILE_PATH = r"G:\Shared drives\99.3 GIS Admin\Production\Layer Files\AEP - Study Area.lyrx"


def _get_token():
    try:
        info = arcpy.GetSigninToken()
        return info.get("token") if info else None
    except Exception:
        return None


def build_project_defq(project_number, layer=None):
    """
    Build a WHERE clause for project_number + EndDate IS NULL.
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


def _normalize_added(added):
    """
    Normalise addDataFromPath return and extract a usable layer object.
    Returns (top_object, child_layer_or_none, parent_object_or_none)
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
    Attempt Headmaster-style swap or ApplySymbologyFromLayer fallback.
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
                        arcpy.management.ApplySymbologyFromLayer(data_layer, style_path)
                        update_ok = True
                        arcpy.AddMessage("  • Applied symbology to data layer via ApplySymbologyFromLayer (fallback).")
                    except Exception as e2:
                        arcpy.AddWarning(f"  - ApplySymbologyFromLayer fallback failed: {e2}")
                except Exception as e:
                    arcpy.AddWarning(f"  - updateConnectionProperties failed: {e}")
                    try:
                        arcpy.management.ApplySymbologyFromLayer(data_layer, style_path)
                        update_ok = True
                        arcpy.AddMessage("  • Applied symbology to data layer via ApplySymbologyFromLayer (fallback).")
                    except Exception as e2:
                        arcpy.AddWarning(f"  - ApplySymbologyFromLayer fallback failed: {e2}")
            else:
                arcpy.AddMessage("  - updateConnectionProperties not available on imported style; attempting ApplySymbologyFromLayer fallback.")
                try:
                    arcpy.management.ApplySymbologyFromLayer(data_layer, style_path)
                    update_ok = True
                    arcpy.AddMessage(f"  • Applied symbology to data layer via ApplySymbologyFromLayer as workaround.")
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
        if update_ok:
            try:
                site_map.removeLayer(data_layer)
            except Exception:
                try:
                    data_layer.visible = False
                except:
                    pass
        else:
            try:
                if parent and parent is not style_layer:
                    try:
                        site_map.removeLayer(parent)
                    except Exception:
                        pass
                try:
                    site_map.removeLayer(style_layer)
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass

    try:
        if parent and parent is not style_layer:
            try:
                site_map.removeLayer(parent)
            except Exception:
                pass
    except Exception:
        pass

    final_layer = style_layer if update_ok else data_layer
    return final_layer


def _cleanup_duplicates(site_map, final_layer, display_name, preexisting_names=None):
    """
    Remove layers with the same display name that were present before this run.
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


def _sanitize_fc_name(name, max_len=63):
    """
    Produce a geodatabase-safe feature class name from an arbitrary display name.
    """
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


def _fetch_service_metadata(service_url, token=None):
    """
    Try sensible metadata endpoints for the given service URL.
    """
    try_urls = []
    base = service_url.rstrip('/')
    try:
        parent = base.rsplit('/', 1)[0]
        try_urls.append(parent + '?f=json')
    except:
        pass
    try_urls.append(base + '?f=json')

    for mu in try_urls:
        murl = mu
        if token:
            sep = '&' if '?' in murl else '?'
            murl = murl + f"&token={token}"
        try:
            with urllib.request.urlopen(murl, timeout=30) as mresp:
                meta = json.loads(mresp.read().decode())
                info = {}
                for k in ("serviceDescription", "name", "type", "currentVersion", "supportsQuery", "capabilities", "maxRecordCount"):
                    if k in meta:
                        info[k] = meta[k]
                if not info:
                    info = {k: meta.get(k, "") for k in ("name", "type", "serviceDescription")}
                return info
        except Exception:
            continue
    return None


def _get_study_area_by_project_number(target_layer_url, token, project_number):
    """
    Query the feature service for the active study area (EndDate IS NULL).
    """
    safe_project_number = project_number.replace("'", "''") if project_number else project_number
    attempts = []
    if safe_project_number and safe_project_number.isdigit():
        attempts.append(f"project_number = {int(safe_project_number)} AND EndDate IS NULL")
    try:
        f = float(safe_project_number)
        if f.is_integer():
            attempts.append(f"project_number = {int(f)} AND EndDate IS NULL")
    except Exception:
        pass
    attempts.append(f"project_number = '{safe_project_number}' AND EndDate IS NULL")

    query_result = None
    for where in attempts:
        params = {"where": where, "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json"}
        if token:
            params["token"] = token
        query_url = f"{target_layer_url}/query?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(query_url, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            if data.get("features"):
                query_result = data
                break
        except Exception:
            continue

    if not query_result:
        return None

    feat = query_result['features'][0]
    sr = query_result.get('spatialReference') or {"wkid": 4326}
    polygon = arcpy.AsShape({"rings": feat['geometry']['rings'], "spatialReference": sr}, True)
    temp_fc = os.path.join("in_memory", f"study_area_{project_number}_{uuid.uuid4().hex[:6]}")
    arcpy.management.CopyFeatures(polygon, temp_fc)

    for fname, fval in feat['attributes'].items():
        if fname not in ("OBJECTID", "GlobalID", "Shape", "Shape_Area", "Shape_Length"):
            try:
                arcpy.management.AddField(temp_fc, fname, "TEXT", field_length=255)
            except Exception:
                pass
    return temp_fc


def _add_fc_to_map_via_layerfile(site_map, fc_path, display_name=None):
    """
    Add feature class via temporary layer file to avoid web_service_type inference issues.
    """
    temp_layer_name = f"tmp_add_{uuid.uuid4().hex[:6]}"
    temp_lyrx = None
    added_layer = None
    try:
        arcpy.management.MakeFeatureLayer(fc_path, temp_layer_name)
        tf = tempfile.gettempdir()
        temp_lyrx = os.path.join(tf, f"tmp_{uuid.uuid4().hex[:8]}.lyrx")
        try:
            if arcpy.Exists(temp_lyrx):
                try:
                    arcpy.management.Delete(temp_lyrx)
                except Exception:
                    pass
            arcpy.management.SaveToLayerFile(temp_layer_name, temp_lyrx, "ABSOLUTE")
            lf = arcpy.mp.LayerFile(temp_lyrx)
            try:
                added = site_map.addLayer(lf)
            except Exception:
                added = site_map.addDataFromPath(temp_lyrx)
            top, child, parent = _normalize_added(added)
            added_layer = child or top
        except Exception as e:
            arcpy.AddWarning(f"  - Could not save/add temporary layerfile for '{fc_path}': {e}\n{traceback.format_exc()}")
            try:
                added = site_map.addDataFromPath(fc_path)
                top, child, parent = _normalize_added(added)
                added_layer = child or top
            except Exception as e2:
                arcpy.AddWarning(f"  - Fallback addDataFromPath also failed for '{fc_path}': {e2}\n{traceback.format_exc()}")
                added_layer = None
    except Exception as e:
        arcpy.AddWarning(f"  - Could not create temporary feature layer for '{fc_path}': {e}\n{traceback.format_exc()}")
        try:
            added = site_map.addDataFromPath(fc_path)
            top, child, parent = _normalize_added(added)
            added_layer = child or top
        except Exception as e2:
            arcpy.AddWarning(f"  - Final fallback addDataFromPath failed for '{fc_path}': {e2}\n{traceback.format_exc()}")
            added_layer = None
    finally:
        try:
            if arcpy.Exists(temp_layer_name):
                arcpy.management.Delete(temp_layer_name)
        except Exception:
            pass
        try:
            if temp_lyrx and os.path.exists(temp_lyrx):
                try:
                    os.remove(temp_lyrx)
                except Exception:
                    pass
        except Exception:
            pass

    try:
        if added_layer and display_name:
            try:
                added_layer.name = display_name
            except Exception:
                pass
    except Exception:
        pass

    return added_layer


def run_import_std_site_layers(project_number, overwrite_flag=False, force_requery=False, study_area_fc=None):
    """
    Main logic for Step 2.
    """
    reference_table_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15"
    target_layer_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"

    arcpy.AddMessage("=" * 60)
    arcpy.AddMessage("STEP 2 - ADD PROJECT LAYERS (Combined Toolbox)")
    arcpy.AddMessage("=" * 60)

    summary = {"success": False, "extracted": [], "replaced": [], "skipped": [], "failed": []}

    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        default_gdb = aprx.defaultGeodatabase
        map_obj = aprx.activeMap
        token = _get_token()

        if not study_area_fc:
            arcpy.AddMessage(f"Retrieving study area for Project {project_number} (EndDate IS NULL)...")
            study_area_fc = _get_study_area_by_project_number(target_layer_url, token, project_number)
            if not study_area_fc:
                arcpy.AddError(f"Could not find an active (EndDate IS NULL) study area for Project {project_number}.")
                return summary

        site_area_m2 = 0.0
        with arcpy.da.SearchCursor(study_area_fc, ["SHAPE@"]) as sc:
            for r in sc:
                site_area_m2 = r[0].getArea("GEODESIC", "SQUAREMETERS")
                break
        arcpy.AddMessage(f"  ✓ Study area size: {site_area_m2:.2f} m²")

        arcpy.AddMessage("Querying Standard Connection Reference Table for ProjectType = 'all' ...")
        params = {"where": "ProjectType='all'", "outFields": "*", "f": "json", "orderByFields": "SortOrder ASC"}
        if token:
            params["token"] = token
        query_url = f"{reference_table_url}/query?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(query_url, timeout=60) as resp:
            ref_data = json.loads(resp.read().decode())

        features = ref_data.get("features", [])
        if not features:
            arcpy.AddWarning("No standard connections found for ProjectType = 'all'.")
        else:
            arcpy.AddMessage(f"  ✓ Found {len(features)} reference records (ordered by SortOrder).")

        processed_outputs = []
        skipped = []
        extracted_new = []
        replaced = []
        failed = []
        fallback_qurls_for_failed = []

        site_map_created_in_run = False
        site_map = None
        maps = [m for m in aprx.listMaps() if m.name == "Site Details Map"]
        if maps:
            site_map = maps[0]
        else:
            try:
                site_map = aprx.createMap("Site Details Map")
                site_map_created_in_run = True
                arcpy.AddMessage("  ✓ Created 'Site Details Map'.")
                try:
                    site_map.addBasemap("Imagery Hybrid")
                except Exception:
                    pass
                try:
                    site_map.spatialReference = arcpy.SpatialReference(8058)
                except Exception:
                    pass
            except Exception as cm_err:
                arcpy.AddWarning(f"  - Could not create 'Site Details Map': {cm_err}")
                site_map = None

        preexisting_layer_names = set()
        try:
            if site_map:
                preexisting_layer_names = {getattr(lyr, "name", "") for lyr in site_map.listLayers() if getattr(lyr, "name", "")}
        except Exception:
            preexisting_layer_names = set()

        if site_map_created_in_run and site_map:
            psa_layer_obj = None
            psa_temp_copy = None
            try:
                add_path = study_area_fc
                needs_temp_copy = False
                try:
                    if isinstance(study_area_fc, str) and (study_area_fc.lower().startswith("in_memory") or study_area_fc.lower().startswith("memory")):
                        needs_temp_copy = True
                except Exception:
                    needs_temp_copy = False

                if needs_temp_copy:
                    psa_temp_copy = os.path.join(default_gdb, f"tmp_psa_{uuid.uuid4().hex[:6]}")
                    try:
                        if arcpy.Exists(psa_temp_copy):
                            arcpy.management.Delete(psa_temp_copy)
                    except Exception:
                        pass
                    arcpy.management.CopyFeatures(study_area_fc, psa_temp_copy)
                    add_path = psa_temp_copy
                    arcpy.AddMessage(f"  • Copied PSA from in_memory to {psa_temp_copy} for reliable map insertion.")

                psa_layer_obj = _add_fc_to_map_via_layerfile(site_map, add_path, display_name=f"Project Study Area {project_number}")

                if psa_layer_obj:
                    final_psa_layer = psa_layer_obj
                    if os.path.exists(LAYERFILE_PATH):
                        try:
                            dq_for_psa = build_project_defq(project_number, layer=psa_layer_obj)
                        except Exception:
                            dq_for_psa = build_project_defq(project_number)
                        try:
                            final = _apply_style_swap(site_map, psa_layer_obj, LAYERFILE_PATH, display_name=f"Project Study Area {project_number}", set_defq=dq_for_psa)
                            if final is not None:
                                final_psa_layer = final
                                arcpy.AddMessage("  ✓ Applied standard Study Area symbology to PSA by swapping.")
                            else:
                                try:
                                    arcpy.management.ApplySymbologyFromLayer(psa_layer_obj, LAYERFILE_PATH)
                                    final_psa_layer = psa_layer_obj
                                    arcpy.AddMessage("  ✓ Applied standard Study Area symbology using ApplySymbologyFromLayer.")
                                except Exception as e_fall:
                                    arcpy.AddWarning(f"  - PSA ApplySymbologyFromLayer fallback failed: {e_fall}\n{traceback.format_exc()}")
                        except Exception as eaddpsa:
                            arcpy.AddWarning(f"  - Could not apply standard symbology to PSA: {eaddpsa}\n{traceback.format_exc()}")
                    try:
                        dq = build_project_defq(project_number, layer=final_psa_layer)
                        if final_psa_layer and final_psa_layer.supports("DEFINITIONQUERY"):
                            final_psa_layer.definitionQuery = dq
                            arcpy.AddMessage("  ✓ Applied definition query to Project Study Area layer.")
                    except Exception:
                        pass
                else:
                    arcpy.AddWarning("  - Project Study Area was not added to the map.")
            except Exception as inner_psa_err:
                arcpy.AddWarning(f"  - Error while adding/styling PSA: {inner_psa_err}\n{traceback.format_exc()}")
            finally:
                try:
                    if psa_temp_copy and arcpy.Exists(psa_temp_copy):
                        arcpy.management.Delete(psa_temp_copy)
                except Exception:
                    pass

            try:
                preexisting_layer_names = {getattr(lyr, "name", "") for lyr in site_map.listLayers() if getattr(lyr, "name", "")}
            except Exception:
                pass

        for idx, feat in enumerate(features, start=1):
            attrs = feat.get("attributes", {})
            def _get_attr_ci(attrs, key):
                for k, v in attrs.items():
                    if k.lower() == key.lower():
                        return v
                return None

            service_url = _get_attr_ci(attrs, "URL") or _get_attr_ci(attrs, "Url") or _get_attr_ci(attrs, "url")
            site_buffer = _get_attr_ci(attrs, "SiteBuffer") or 0
            buffer_action = _get_attr_ci(attrs, "BufferAction") or "INTERSECT"
            feature_dataset_name = _get_attr_ci(attrs, "FeatureDatasetName") or "ProjectData"
            short_name = _get_attr_ci(attrs, "ShortName") or f"Layer_{idx}"
            style_file = _get_attr_ci(attrs, "Style") or _get_attr_ci(attrs, "LayerFile")

            if style_file:
                try:
                    style_file = str(style_file).strip().strip('\'"')
                    style_file = os.path.normpath(style_file)
                except Exception:
                    pass

            safe_short = _sanitize_fc_name(short_name)
            arcpy.AddMessage(f"Processing {idx}: {short_name} (Buffer: {site_buffer})")

            if not service_url:
                skipped.append(short_name)
                continue

            fd_path = os.path.join(default_gdb, feature_dataset_name)
            out_fc = os.path.join(fd_path, safe_short)

            if arcpy.Exists(out_fc):
                if not overwrite_flag and not force_requery:
                    arcpy.AddMessage(f"  - Output {out_fc} already exists (SKIP)")
                    skipped.append(short_name)
                    continue
                else:
                    arcpy.AddMessage(f"  - Output {out_fc} exists. Refreshing...")

            try:
                distance_m = float(site_buffer) if site_buffer not in (None, '') else 0.0
            except:
                distance_m = 0.0

            if distance_m > 0:
                buffer_fc = os.path.join("in_memory", f"buf_{safe_short}_{int(time.time())}")
                if arcpy.Exists(buffer_fc):
                    arcpy.management.Delete(buffer_fc)
                arcpy.analysis.Buffer(study_area_fc, buffer_fc, f"{distance_m} Meters", method="GEODESIC")
            else:
                buffer_fc = study_area_fc

            temp_layer_name = f"temp_layer_{idx}_{int(time.time())}"
            made_layer = False
            try:
                arcpy.management.MakeFeatureLayer(service_url, temp_layer_name)
                made_layer = True
            except Exception as e:
                arcpy.AddWarning(f"  - MakeFeatureLayer failed for '{service_url}': {e}")

            selection_succeeded = False
            qurl_used = None
            qdata = None
            try:
                if made_layer:
                    arcpy.management.SelectLayerByLocation(temp_layer_name, "INTERSECT", buffer_fc)
                    selection_succeeded = True
                else:
                    raise Exception("Layer creation failed; attempting REST fallback")
            except Exception as sel_err:
                # REST fallback logic
                try:
                    if arcpy.Exists(temp_layer_name):
                        arcpy.management.Delete(temp_layer_name)
                    geom_json = None
                    geom_sr_wkid = 4326
                    with arcpy.da.SearchCursor(buffer_fc, ["SHAPE@"]) as gcur:
                        for grow in gcur:
                            geom_obj = grow[0]
                            try:
                                geom_json = geom_obj.JSON
                            except:
                                geom_json = None
                            try:
                                geom_sr_wkid = int(getattr(geom_obj.spatialReference, "factoryCode", 4326))
                            except Exception:
                                pass
                            break

                    if not geom_json:
                        raise Exception("No geometry available for fallback query")

                    query_layer_url = service_url.rstrip('/') + "/query"
                    qparams = {
                        "geometry": geom_json,
                        "geometryType": "esriGeometryPolygon",
                        "spatialRel": "esriSpatialRelIntersects",
                        "inSR": str(geom_sr_wkid),
                        "returnIdsOnly": "true",
                        "f": "json"
                    }
                    if token:
                        qparams["token"] = token

                    object_ids = []
                    last_err = None
                    for attempt in range(3):
                        qurl = f"{query_layer_url}?{urllib.parse.urlencode(qparams)}"
                        qurl_used = qurl
                        try:
                            with urllib.request.urlopen(qurl, timeout=120) as qresp:
                                qdata = json.loads(qresp.read().decode())
                            if "error" in qdata:
                                last_err = qdata["error"]
                                time.sleep(2)
                                continue
                            object_ids = qdata.get("objectIds") or []
                            break
                        except Exception as e:
                            last_err = e
                            time.sleep(2)

                    if not object_ids:
                        failed.append(short_name)
                        fallback_qurls_for_failed.append({"shortname": short_name, "qurl": qurl_used, "error": str(last_err)})
                        continue

                    oid_field = qdata.get("objectIdFieldName") or "OBJECTID"
                    id_list = ",".join(str(int(i)) for i in object_ids)
                    where_ids = f"{oid_field} IN ({id_list})"
                    arcpy.management.MakeFeatureLayer(service_url, temp_layer_name, where_clause=where_ids)
                    selection_succeeded = True

                except Exception as fb_err:
                    failed.append(short_name)
                    fallback_qurls_for_failed.append({"shortname": short_name, "qurl": qurl_used, "error": str(fb_err)})
                    continue

            if not selection_succeeded:
                failed.append(short_name)
                continue

            count = int(arcpy.management.GetCount(temp_layer_name).getOutput(0))
            if count < 1:
                skipped.append(short_name)
                try:
                    arcpy.management.Delete(temp_layer_name)
                except:
                    pass
                continue

            if not arcpy.Exists(fd_path):
                arcpy.management.CreateFeatureDataset(default_gdb, feature_dataset_name, arcpy.SpatialReference(8058))

            timestamp = int(time.time())
            tmp_out = os.path.join(default_gdb, f"tmp_extract_{safe_short}_{timestamp}_{uuid.uuid4().hex[:6]}")
            try:
                if buffer_action and buffer_action.strip().upper() == "CLIP":
                    arcpy.analysis.Clip(temp_layer_name, buffer_fc, tmp_out)
                else:
                    arcpy.management.CopyFeatures(temp_layer_name, tmp_out)
            except Exception as e:
                failed.append(short_name)
                try:
                    arcpy.management.Delete(tmp_out)
                except:
                    pass
                continue

            # Add ExtractDate & ExtractURL
            try:
                if not arcpy.ListFields(tmp_out, "ExtractDate"):
                    arcpy.management.AddField(tmp_out, "ExtractDate", "DATE")
                if not arcpy.ListFields(tmp_out, "ExtractURL"):
                    arcpy.management.AddField(tmp_out, "ExtractURL", "TEXT", field_length=2048)
                now_dt = datetime.now()
                with arcpy.da.UpdateCursor(tmp_out, ["ExtractDate", "ExtractURL"]) as uc:
                    for row in uc:
                        row[0] = now_dt
                        row[1] = service_url
                        uc.updateRow(row)
            except Exception:
                pass

            try:
                if arcpy.Exists(out_fc):
                    arcpy.management.Delete(out_fc)
                    replaced.append(short_name)
                else:
                    extracted_new.append(short_name)

                arcpy.management.CopyFeatures(tmp_out, out_fc)
                try:
                    arcpy.management.Delete(tmp_out)
                except:
                    pass

                processed_outputs.append({"shortname": short_name, "path": out_fc, "style": style_file, "safe_short": safe_short})

                if site_map:
                    final_layer = _add_fc_to_map_via_layerfile(site_map, out_fc, display_name=short_name)
                    if final_layer and style_file:
                        style_path = os.path.expanduser(style_file)
                        try_paths = [style_path, os.path.join(default_gdb, style_path)]
                        applied = False
                        for sp in try_paths:
                            if os.path.exists(sp):
                                final_after = _apply_style_swap(site_map, final_layer, sp, display_name=short_name)
                                if final_after:
                                    final_layer = final_after
                                    applied = True
                                    break
                                else:
                                    try:
                                        arcpy.management.ApplySymbologyFromLayer(final_layer, sp)
                                        applied = True
                                        break
                                    except Exception:
                                        continue
                    
                    try:
                        _cleanup_duplicates(site_map, final_layer, short_name, preexisting_names=preexisting_layer_names)
                    except Exception:
                        pass
            except Exception as e:
                failed.append(short_name)
                continue
            
            # cleanup per loop
            try:
                if arcpy.Exists(temp_layer_name):
                    arcpy.management.Delete(temp_layer_name)
                if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                    arcpy.management.Delete(buffer_fc)
            except:
                pass

        # Create SiteLotsReport
        lots_fc = None
        for po in processed_outputs:
            if "lot" in po["shortname"].lower():
                lots_fc = po["path"]
                break

        if lots_fc:
            lots_layer = f"temp_lots_layer_{uuid.uuid4().hex[:6]}"
            try:
                arcpy.management.MakeFeatureLayer(lots_fc, lots_layer)
                arcpy.management.SelectLayerByLocation(lots_layer, "WITHIN", study_area_fc)
                report_table = os.path.join(default_gdb, "SiteLotsReport")
                if arcpy.Exists(report_table):
                    arcpy.management.Delete(report_table)
                arcpy.management.CreateTable(default_gdb, "SiteLotsReport")
                arcpy.management.AddField(report_table, "Lot", "TEXT", field_length=50)
                arcpy.management.AddField(report_table, "Section", "TEXT", field_length=50)
                arcpy.management.AddField(report_table, "Plan", "TEXT", field_length=50)
                arcpy.management.AddField(report_table, "PlanLotArea", "DOUBLE")
                arcpy.management.AddField(report_table, "PlanLotAreaUnits", "TEXT", field_length=50)

                src_fields = [f.name for f in arcpy.ListFields(lots_fc)]
                def find_field(names):
                    for name in names:
                        for f in src_fields:
                            if f.lower() == name.lower():
                                return f
                    return None

                f_map = {
                    "Lot": find_field(["lotnumber", "lot_no", "lot"]),
                    "Section": find_field(["sectionnumber", "section_no", "section"]),
                    "Plan": find_field(["plannumber", "plan_number", "plan"]),
                    "PlanLotArea": find_field(["planlotarea", "plan_lot_area", "planlotarea"]),
                    "PlanLotAreaUnits": find_field(["planlotareaunits", "plan_lot_area_units"])
                }
                
                insert_fields = ["Lot", "Section", "Plan", "PlanLotArea", "PlanLotAreaUnits"]
                actual_read = [f_map[k] for k in insert_fields]
                
                if any(actual_read):
                    with arcpy.da.InsertCursor(report_table, insert_fields) as ins, arcpy.da.SearchCursor(lots_layer, [f if f else "OBJECTID" for f in actual_read]) as src:
                        for srow in src:
                            out_row = []
                            for i, fld in enumerate(actual_read):
                                if fld:
                                    out_row.append(srow[i])
                                else:
                                    out_row.append(None)
                            ins.insertRow(out_row)
                    arcpy.AddMessage(f"  ✓ SiteLotsReport created: {report_table}")
            except Exception as e:
                arcpy.AddWarning(f"  - Error creating SiteLotsReport: {e}")
            finally:
                if arcpy.Exists(lots_layer):
                    arcpy.management.Delete(lots_layer)

        # Final Summary
        arcpy.AddMessage("\n" + ("✨" * 12))
        arcpy.AddMessage("🌈 FUNKY FINAL REPORT — STEP 2 🌈")
        arcpy.AddMessage("-" * 50)
        arcpy.AddMessage(f"Project: {project_number}")
        arcpy.AddMessage(f"New: {len(extracted_new)} | Replaced: {len(replaced)} | Skipped: {len(skipped)} | Failed: {len(failed)}")
        arcpy.AddMessage("-" * 50)
        arcpy.AddMessage("STEP 2 COMPLETE.")

        summary["success"] = True
        summary["extracted"] = extracted_new
        summary["replaced"] = replaced
        summary["skipped"] = skipped
        summary["failed"] = failed

    except Exception as e:
        arcpy.AddError(f"Error executing Step 2: {str(e)}\n{traceback.format_exc()}")

    return summary


# ------------------------------------------------------------------------------
# TOOLBOX CLASSES
# [cite_start](Refactored from ImportStdSiteLayers.pyt [cite: 1, 2])
# ------------------------------------------------------------------------------

class Toolbox(object):
    def __init__(self):
        self.label = "Import Standard Site Layers (Split Step 2)"
        self.alias = "ImportStdSiteLayers"
        self.tools = [ImportStdSiteLayersTool]

class ImportStdSiteLayersTool(object):
    def __init__(self):
        self.label = "Import Standard Site Layers"
        self.description = "Adds standard project layers based on the subject site (Step 2, refactored)."
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Project Number (choose Study Area)",
            name="project_number_choice",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param0.filter.list = []
        param0.value = "6666"

        param1 = arcpy.Parameter(
            displayName="Overwrite existing project data",
            name="overwrite_existing",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param1.value = False

        param2 = arcpy.Parameter(
            displayName="Force re-query even if output exists (refresh)",
            name="force_requery",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param2.value = False

        return [param0, param1, param2]

    def updateParameters(self, parameters):
        # Attempt to refresh the project number list
        try:
            # [cite_start]Replaced call to module with local call [cite: 8]
            token = _get_token()
            target_layer_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"
            params = {"where": "EndDate IS NULL", "outFields": "project_number", "returnDistinctValues": "true", "f": "json"}
            if token:
                params["token"] = token
            query_url = f"{target_layer_url}/query?{urllib.parse.urlencode(params)}"
            try:
                with urllib.request.urlopen(query_url, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
                values = sorted({str(feat['attributes'].get('project_number')) for feat in data.get('features', []) if feat['attributes'].get('project_number') is not None})
                parameters[0].filter.list = values
                if parameters[0].valueAsText and parameters[0].valueAsText in values:
                    parameters[0].value = parameters[0].valueAsText
            except Exception:
                pass
        except Exception:
            pass
        return

    def updateMessages(self, parameters):
        p_proj_num = parameters[0]
        if p_proj_num.altered:
            val = p_proj_num.valueAsText
            if val and (not val.isdigit() or len(val) > 5):
                p_proj_num.setErrorMessage("Project Number must be 5 digits or less (numeric).")
        return

    def isLicensed(self):
        return True

    def execute(self, parameters, messages):
        # [cite_start]Removed dependency check on 'import_std_mod' [cite: 13, 14]
        project_number = parameters[0].valueAsText
        overwrite_flag = bool(parameters[1].value) if len(parameters) > 1 else False
        force_requery = bool(parameters[2].value) if len(parameters) > 2 else False

        arcpy.AddMessage("Calling internal run_import_std_site_layers(...)")
        try:
            # [cite_start]Replaced call to module with local call [cite: 14]
            res = run_import_std_site_layers(project_number, overwrite_flag=overwrite_flag, force_requery=force_requery)
            arcpy.AddMessage(f"ImportStdSiteLayers result: {res}")
            if not res.get("success"):
                arcpy.AddError("ImportStdSiteLayers reported failure. Check messages above.")
        except Exception as e:
            arcpy.AddError(f"Error running ImportStdSiteLayers: {e}\n{traceback.format_exc()}")
        return
