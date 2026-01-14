# ImportStdSiteLayers.py
# Standalone script containing the refactored "Step 2 - Add Standard Project Layers" logic.
# Designed to be imported by a Python toolbox (ImportStdSiteLayers.pyt) or executed directly.
#
# This script focuses on Step 2 only: it can either accept a study_area_fc (feature class path)
# produced elsewhere (e.g., from CreateSiteByProperty.run_create_site) or it will fetch the
# authoritative study area for a given project number from the Project_Study_Area service.
#
# Dependencies: arcpy, Python standard libs (os, json, urllib, datetime, time, re, uuid, traceback, tempfile)

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
import tempfile

# Styling layerfile (same as original)
LAYERFILE_PATH = r"G:\Shared drives\99.3 GIS Admin\Production\Layer Files\AEP - Study Area.lyrx"


def _get_token():
    try:
        info = arcpy.GetSigninToken()
        return info.get("token") if info else None
    except Exception:
        return None


def build_project_defq(project_number, layer=None):
    """
    Build a WHERE clause for project_number + EndDate IS NULL that attempts to
    respect the target field type when a layer object/path is available.
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
    Normalise addDataFromPath return and extract a usable layer object
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
    Attempt Headmaster-style swap:
    - import style (addDataFromPath)
    - extract actual style sublayer
    - updateConnectionProperties to point at data_layer connection
    - if updateConnectionProperties fails, try ApplySymbologyFromLayer on the data_layer
    - set definition query on style layer if provided and supported
    - remove original data_layer and any parent imported group (only if style layer is successfully re-pointed)
    Returns final_layer (the styled layer or data_layer if only symbology applied) or None on complete failure.
    """
    final_layer = data_layer

    # Attempt to inspect the layerfile first to find a preferred inner layer name (best-effort)
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
    # If preferred layer name detected, try to find that child under top
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

    # capture connection and def query from data_layer
    try:
        conn_props = data_layer.connectionProperties
    except Exception:
        conn_props = None
    try:
        def_query = data_layer.definitionQuery if data_layer.supports("DEFINITIONQUERY") else None
    except Exception:
        def_query = None

    update_ok = False
    # try to update connection properties on style_layer
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

    # restore def query from data_layer (or provided)
    try:
        if set_defq and style_layer.supports("DEFINITIONQUERY"):
            style_layer.definitionQuery = set_defq
        elif def_query and style_layer.supports("DEFINITIONQUERY"):
            style_layer.definitionQuery = def_query
    except Exception:
        pass

    # rename style layer to display_name if provided
    try:
        if display_name:
            style_layer.name = display_name
    except Exception:
        pass

    # If we successfully updated the style layer's connection to point to the data layer,
    # remove the original data layer (only after we've attempted to apply symbology)
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
            # If we couldn't update the imported style layer's connection, prefer to keep data_layer
            # and remove the imported style wrapper to avoid leaving a disconnected layer in the map.
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

    # remove parent import wrapper if it's a group and different from style_layer
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
                # skip the final layer by name + longName check
                if getattr(lyr, "name", "") == final_name:
                    try:
                        if getattr(lyr, "longName", "") == getattr(final_layer, "longName", ""):
                            continue
                    except Exception:
                        if lyr is final_layer:
                            continue

                # Only consider layers that match the display_name
                if getattr(lyr, "name", "") != display_name:
                    continue

                # If we have a list of preexisting names, only remove layers that were present before we ran.
                if preexisting_names is not None:
                    if display_name not in preexisting_names:
                        # Do not remove layers we did not previously have in the map
                        continue
                    # remove the layer that was preexisting (and matches the name)
                    try:
                        site_map.removeLayer(lyr)
                        arcpy.AddMessage(f"  • Removed pre-existing duplicate layer '{display_name}'.")
                    except Exception:
                        try:
                            lyr.visible = False
                        except Exception:
                            pass
                else:
                    # Conservative fallback: don't delete — hide instead and log
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
    Try a couple of sensible metadata endpoints for the given service URL and return a small dict
    with a few useful fields (if available). This is optional and best-effort.
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
    Query the feature service for the active study area (EndDate IS NULL) for project_number.
    Returns an in_memory feature class path (temp FC) or None.
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

    # Add basic attributes back (best-effort)
    for fname, fval in feat['attributes'].items():
        if fname not in ("OBJECTID", "GlobalID", "Shape", "Shape_Area", "Shape_Length"):
            try:
                arcpy.management.AddField(temp_fc, fname, "TEXT", field_length=255)
            except Exception:
                pass

    return temp_fc


def _add_fc_to_map_via_layerfile(site_map, fc_path, display_name=None):
    """
    Add a feature class to the map by creating a temporary feature layer then saving it
    to a temporary layer file and adding that layerfile to the map. This avoids addDataFromPath's
    AUTOMATIC web_service_type inference which can fail for some datasource strings.
    Returns the added map layer object, or None on failure.
    """
    temp_layer_name = f"tmp_add_{uuid.uuid4().hex[:6]}"
    temp_lyrx = None
    added_layer = None
    try:
        # Create an ephemeral feature layer
        arcpy.management.MakeFeatureLayer(fc_path, temp_layer_name)
        # Save to a temporary layer file
        tf = tempfile.gettempdir()
        temp_lyrx = os.path.join(tf, f"tmp_{uuid.uuid4().hex[:8]}.lyrx")
        try:
            if arcpy.Exists(temp_lyrx):
                try:
                    arcpy.management.Delete(temp_lyrx)
                except Exception:
                    pass
            arcpy.management.SaveToLayerFile(temp_layer_name, temp_lyrx, "ABSOLUTE")
            # Add via LayerFile which avoids AUTOMATIC web_service_type problems
            lf = arcpy.mp.LayerFile(temp_lyrx)
            try:
                added = site_map.addLayer(lf)
            except Exception:
                # fallback to addDataFromPath on the layerfile
                added = site_map.addDataFromPath(temp_lyrx)
            top, child, parent = _normalize_added(added)
            added_layer = child or top
        except Exception as e:
            arcpy.AddWarning(f"  - Could not save/add temporary layerfile for '{fc_path}': {e}\n{traceback.format_exc()}")
            # fallback: try addDataFromPath directly on the fc_path
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
            # final fallback
            added = site_map.addDataFromPath(fc_path)
            top, child, parent = _normalize_added(added)
            added_layer = child or top
        except Exception as e2:
            arcpy.AddWarning(f"  - Final fallback addDataFromPath failed for '{fc_path}': {e2}\n{traceback.format_exc()}")
            added_layer = None
    finally:
        # delete the in-memory temp layer if it exists
        try:
            if arcpy.Exists(temp_layer_name):
                arcpy.management.Delete(temp_layer_name)
        except Exception:
            pass
        # remove temporary layer file
        try:
            if temp_lyrx and os.path.exists(temp_lyrx):
                try:
                    os.remove(temp_lyrx)
                except Exception:
                    pass
        except Exception:
            pass

    # rename if requested
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
    Main entrypoint for Step 2 processing.

    Parameters:
        project_number (str): project number to use to find the study area (if study_area_fc is None)
        overwrite_flag (bool): whether to overwrite existing outputs
        force_requery (bool): whether to re-query services even if outputs exist
        study_area_fc (str): optional path to a study area feature class to use instead of querying the service

    Returns:
        dict summary: {success: bool, extracted: [...], replaced: [...], skipped: [...], failed: [...]}
    """
    reference_table_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Standard_Connection_Reference_Table/FeatureServer/15"
    target_layer_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"

    arcpy.AddMessage("=" * 60)
    arcpy.AddMessage("STEP 2 - ADD PROJECT LAYERS (refactored standalone)")
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

        # compute total site area in square meters for later use (geodesic)
        site_area_m2 = 0.0
        with arcpy.da.SearchCursor(study_area_fc, ["SHAPE@"]) as sc:
            for r in sc:
                site_area_m2 = r[0].getArea("GEODESIC", "SQUAREMETERS")
                break

        arcpy.AddMessage(f"  ✓ Study area size: {site_area_m2:.2f} m²")

        # Query the Standard Connection Reference Table for ProjectType = "all"
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

        # Prepare/possible map creation for Site Details Map (to add layers into)
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
                    arcpy.AddMessage("  ✓ Applied 'Imagery Hybrid' basemap to 'Site Details Map'.")
                except Exception:
                    arcpy.AddWarning("  - Could not apply 'Imagery Hybrid' basemap programmatically.")
                try:
                    site_map.spatialReference = arcpy.SpatialReference(8058)
                    arcpy.AddMessage("  ✓ Set 'Site Details Map' spatial reference to GDA2020 / NSW Lambert (8058).")
                except Exception:
                    arcpy.AddWarning("  - Could not set spatial reference on 'Site Details Map' programmatically.")
            except Exception as cm_err:
                arcpy.AddWarning(f"  - Could not create 'Site Details Map': {cm_err}")
                site_map = None

        preexisting_layer_names = set()
        try:
            if site_map:
                preexisting_layer_names = {getattr(lyr, "name", "") for lyr in site_map.listLayers() if getattr(lyr, "name", "")}
        except Exception:
            preexisting_layer_names = set()

        # If we created the map just now, add the PSA first and style it (so it sits at root).
        if site_map_created_in_run and site_map:
            psa_layer_obj = None
            psa_temp_copy = None
            try:
                # If study_area_fc is in_memory, copy to default_gdb to ensure a FGDB-backed layer is added.
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

                # Use helper that adds via a temporary layerfile to avoid AUTOMATIC inference errors
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
                    arcpy.AddWarning("  - Project Study Area was not added to the map; continuing without a PSA layer in the Site Details Map.")
            except Exception as inner_psa_err:
                arcpy.AddWarning(f"  - Error while adding/styling PSA: {inner_psa_err}\n{traceback.format_exc()}")
            finally:
                # Cleanup any temporary PSA copy we created in the default_gdb
                try:
                    if psa_temp_copy and arcpy.Exists(psa_temp_copy):
                        arcpy.management.Delete(psa_temp_copy)
                except Exception:
                    pass

            # Refresh preexisting names (PSA now present but considered new)
            try:
                preexisting_layer_names = {getattr(lyr, "name", "") for lyr in site_map.listLayers() if getattr(lyr, "name", "")}
            except Exception:
                pass

        # Process reference table records
        for idx, feat in enumerate(features, start=1):
            attrs = feat.get("attributes", {})
            def _get_attr_ci(attrs, key):
                for k, v in attrs.items():
                    if k.lower() == key.lower():
                        return v
                return None

            service_url = _get_attr_ci(attrs, "URL") or _get_attr_ci(attrs, "Url") or _get_attr_ci(attrs, "url")
            site_buffer = _get_attr_ci(attrs, "SiteBuffer") or _get_attr_ci(attrs, "sitebuffer") or 0
            buffer_action = _get_attr_ci(attrs, "BufferAction") or _get_attr_ci(attrs, "bufferaction") or "INTERSECT"
            feature_dataset_name = _get_attr_ci(attrs, "FeatureDatasetName") or _get_attr_ci(attrs, "FeatureDataset") or "ProjectData"
            short_name = _get_attr_ci(attrs, "ShortName") or _get_attr_ci(attrs, "Shortname") or f"Layer_{idx}"
            style_file = _get_attr_ci(attrs, "Style") or _get_attr_ci(attrs, "LayerFile") or _get_attr_ci(attrs, "lyrx")

            raw_style_file = style_file
            if style_file:
                try:
                    style_file = str(style_file).strip().strip('\'"')
                    try:
                        style_file = os.path.normpath(style_file)
                    except Exception:
                        pass
                except Exception:
                    pass
            if raw_style_file != style_file:
                arcpy.AddMessage(f"  • Normalized style field: '{raw_style_file}' -> '{style_file or ''}'")

            safe_short = _sanitize_fc_name(short_name)
            service_url_msg = service_url or ""
            style_file_msg = style_file or ""
            arcpy.AddMessage(f"Processing reference record {idx}: ShortName='{short_name}' (safe: '{safe_short}') URL='{service_url_msg}' Buffer={site_buffer} Action={buffer_action} Style='{style_file_msg}'")

            if not service_url:
                arcpy.AddWarning(f"  - No URL for reference record {short_name}; skipping.")
                skipped.append(short_name)
                continue

            try:
                svc_type = None
                if "/MapServer" in service_url:
                    svc_type = "MapServer"
                elif "/FeatureServer" in service_url:
                    svc_type = "FeatureServer"
                else:
                    svc_type = "UnknownServiceType"
                arcpy.AddMessage(f"  • Service type hint: {svc_type}")
            except Exception:
                pass

            fd_path = os.path.join(default_gdb, feature_dataset_name)
            out_fc = os.path.join(fd_path, safe_short)

            # Quick existence check
            if arcpy.Exists(out_fc):
                if not overwrite_flag and not force_requery:
                    arcpy.AddMessage(f"  - Output {out_fc} already exists. Overwrite disabled and force re-query not set -> SKIP")
                    skipped.append(short_name)
                    continue
                else:
                    arcpy.AddMessage(f"  - Output {out_fc} exists. Will refresh via temporary extract and replace after success.")

            # Buffer the subject site by SiteBuffer (meters)
            try:
                distance_m = float(site_buffer) if site_buffer not in (None, '') else 0.0
            except:
                distance_m = 0.0

            if distance_m > 0:
                buffer_fc = os.path.join("in_memory", f"buf_{safe_short}_{int(time.time())}")
                if arcpy.Exists(buffer_fc):
                    try:
                        arcpy.management.Delete(buffer_fc)
                    except:
                        pass
                arcpy.analysis.Buffer(study_area_fc, buffer_fc, f"{distance_m} Meters", method="GEODESIC")
            else:
                buffer_fc = study_area_fc

            # Connect to target layer and subset by buffer polygon
            temp_layer_name = f"temp_layer_{idx}_{int(time.time())}"
            made_layer = False
            try:
                arcpy.management.MakeFeatureLayer(service_url, temp_layer_name)
                made_layer = True
            except Exception as e:
                arcpy.AddWarning(f"  - Could not make feature layer from URL '{service_url}': {e}\n{traceback.format_exc()}")

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
                arcpy.AddWarning(f"  - Selection by location failed for '{short_name}': {sel_err}\n{traceback.format_exc()}")

                try:
                    meta = _fetch_service_metadata(service_url, token)
                    if meta:
                        arcpy.AddMessage(f"  • Service metadata (best-effort): {meta}")
                    else:
                        arcpy.AddMessage("  • No service metadata available (best-effort).")
                except Exception:
                    pass

                try:
                    if arcpy.Exists(temp_layer_name):
                        arcpy.management.Delete(temp_layer_name)
                    # REST fallback
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
                                if geom_json:
                                    gj = json.loads(geom_json)
                                    sr = gj.get("spatialReference") or {}
                                    geom_sr_wkid = sr.get("wkid") or sr.get("latestWkid") or geom_sr_wkid
                            except Exception:
                                pass
                            try:
                                geom_sr_wkid = int(getattr(geom_obj.spatialReference, "factoryCode", getattr(geom_obj.spatialReference, "wkid", geom_sr_wkid)))
                            except Exception:
                                pass
                            break

                    if not geom_json:
                        arcpy.AddWarning(f"  - Could not obtain geometry JSON for fallback on '{short_name}'.")
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

                    # Retry loop for fallback query (attempt up to 3 times with backoff).
                    object_ids = []
                    last_err = None
                    attempt = 0
                    max_attempts = 3
                    tried_without_token = False

                    while attempt < max_attempts:
                        qurl = f"{query_layer_url}?{urllib.parse.urlencode(qparams)}"
                        qurl_used = qurl
                        arcpy.AddMessage(f"  - REST fallback query URL (attempt {attempt+1}{' (no token)' if tried_without_token else ''}): {qurl}")
                        try:
                            with urllib.request.urlopen(qurl, timeout=120) as qresp:
                                qdata = json.loads(qresp.read().decode())
                            if "error" in qdata:
                                last_err = qdata["error"]
                                arcpy.AddWarning(f"  - REST fallback returned error: {last_err}")
                                try:
                                    err_code = int(last_err.get("code", 0)) if isinstance(last_err, dict) else 0
                                except Exception:
                                    err_code = 0
                                if err_code == 498 and not tried_without_token:
                                    if "token" in qparams:
                                        qparams.pop("token", None)
                                    tried_without_token = True
                                    arcpy.AddMessage("  - Received 498 Invalid Token; retrying fallback without token.")
                                    continue
                                attempt += 1
                                time.sleep(3)
                                continue
                            object_ids = qdata.get("objectIds") or []
                            break
                        except Exception as e:
                            last_err = e
                            arcpy.AddWarning(f"  - REST fallback HTTP error on attempt {attempt+1}: {e}\n{traceback.format_exc()}")
                            attempt += 1
                            time.sleep(3)

                    if not object_ids:
                        arcpy.AddMessage(f"  - REST query returned no features for '{short_name}'; skipping.")
                        failed.append(short_name)
                        fallback_qurls_for_failed.append({"shortname": short_name, "qurl": qurl_used, "error": str(last_err)})
                        if arcpy.Exists(temp_layer_name):
                            try:
                                arcpy.management.Delete(temp_layer_name)
                            except:
                                pass
                        continue

                    oid_field = qdata.get("objectIdFieldName") or "OBJECTID"
                    id_list = ",".join(str(int(i)) for i in object_ids)
                    where_ids = f"{oid_field} IN ({id_list})"
                    try:
                        arcpy.management.MakeFeatureLayer(service_url, temp_layer_name, where_clause=where_ids)
                    except Exception as e2:
                        arcpy.AddWarning(f"  - Could not create filtered layer from service for '{short_name}': {e2}\n{traceback.format_exc()}")
                        failed.append(short_name)
                        fallback_qurls_for_failed.append({"shortname": short_name, "qurl": qurl_used, "error": str(e2)})
                        if arcpy.Exists(temp_layer_name):
                            try:
                                arcpy.management.Delete(temp_layer_name)
                            except:
                                pass
                        continue

                    selection_succeeded = True

                except Exception as fb_err:
                    arcpy.AddWarning(f"  - REST fallback failed for '{short_name}': {fb_err}\n{traceback.format_exc()}")
                    failed.append(short_name)
                    if arcpy.Exists(temp_layer_name):
                        try:
                            arcpy.management.Delete(temp_layer_name)
                        except:
                            pass
                    fallback_qurls_for_failed.append({"shortname": short_name, "qurl": qurl_used if 'qurl_used' in locals() else None, "error": str(fb_err)})
                    continue

            # At this point selection_succeeded indicates a usable temp_layer_name
            if not selection_succeeded:
                arcpy.AddWarning(f"  - Could not select features for '{short_name}'; skipping.")
                if arcpy.Exists(temp_layer_name):
                    try:
                        arcpy.management.Delete(temp_layer_name)
                    except:
                        pass
                if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                    try:
                        arcpy.management.Delete(buffer_fc)
                    except:
                        pass
                failed.append(short_name)
                continue

            count = int(arcpy.management.GetCount(temp_layer_name).getOutput(0))
            arcpy.AddMessage(f"  - Selected {count} features from service.")

            if count < 1:
                arcpy.AddMessage(f"  - No features selected for '{short_name}', skipping.")
                try:
                    arcpy.management.Delete(temp_layer_name)
                except:
                    pass
                if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                    try:
                        arcpy.management.Delete(buffer_fc)
                    except:
                        pass
                skipped.append(short_name)
                continue

            # Ensure feature dataset exists in default GDB
            if not arcpy.Exists(fd_path):
                arcpy.AddMessage(f"  - Creating feature dataset '{feature_dataset_name}' in default geodatabase.")
                arcpy.management.CreateFeatureDataset(default_gdb, feature_dataset_name, arcpy.SpatialReference(8058))

            # Write to a temporary output first (in default_gdb) then replace existing only on success
            timestamp = int(time.time())
            tmp_out = os.path.join(default_gdb, f"tmp_extract_{safe_short}_{timestamp}_{uuid.uuid4().hex[:6]}")
            try:
                if buffer_action and buffer_action.strip().upper() == "CLIP":
                    arcpy.analysis.Clip(temp_layer_name, buffer_fc, tmp_out)
                else:
                    arcpy.management.CopyFeatures(temp_layer_name, tmp_out)
            except Exception as e:
                arcpy.AddWarning(f"  - Error extracting features for '{short_name}': {e}\n{traceback.format_exc()}")
                try:
                    arcpy.management.Delete(temp_layer_name)
                except:
                    pass
                if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                    try:
                        arcpy.management.Delete(buffer_fc)
                    except:
                        pass
                failed.append(short_name)
                try:
                    if arcpy.Exists(tmp_out):
                        arcpy.management.Delete(tmp_out)
                except:
                    pass
                continue

            # Add ExtractDate & ExtractURL fields on tmp_out
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
            except Exception as e:
                arcpy.AddWarning(f"  - Could not add/populate ExtractDate/ExtractURL for '{short_name}': {e}\n{traceback.format_exc()}")

            # Now replace the existing out_fc only after tmp_out was successfully created
            try:
                if arcpy.Exists(out_fc):
                    try:
                        arcpy.management.Delete(out_fc)
                        arcpy.AddMessage(f"  - Deleted existing {out_fc}")
                    except Exception as e:
                        arcpy.AddWarning(f"  - Could not delete existing output {out_fc}: {e}. Will attempt to clean up tmp and skip replacing.\n{traceback.format_exc()}")
                        try:
                            arcpy.management.Delete(tmp_out)
                        except:
                            pass
                        failed.append(short_name)
                        try:
                            arcpy.management.Delete(temp_layer_name)
                        except:
                            pass
                        if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                            try:
                                arcpy.management.Delete(buffer_fc)
                            except:
                                pass
                        continue
                    replaced.append(short_name)
                else:
                    extracted_new.append(short_name)

                # Copy tmp_out to final location
                arcpy.management.CopyFeatures(tmp_out, out_fc)
                try:
                    arcpy.management.Delete(tmp_out)
                except:
                    pass

                arcpy.AddMessage(f"  ✓ Extracted '{short_name}' to {out_fc}")
                processed_outputs.append({"shortname": short_name, "path": out_fc, "style": style_file, "fd": feature_dataset_name, "safe_short": safe_short})

                # Add to map and apply style (ensure it's the FGDB feature class that is added and styled)
                try:
                    if site_map:
                        final_layer = _add_fc_to_map_via_layerfile(site_map, out_fc, display_name=short_name)

                        if not final_layer:
                            arcpy.AddWarning(f"  - Could not add FGDB layer for '{short_name}' to map; skipping styling and map placement for this layer.")
                        else:
                            if style_file:
                                style_path = os.path.expanduser(style_file)
                                if not os.path.isabs(style_path):
                                    try_paths = [
                                        style_path,
                                        os.path.join(os.path.dirname(arcpy.mp.ArcGISProject("CURRENT").filePath or ""), style_path),
                                        os.path.join(default_gdb, style_path)
                                    ]
                                else:
                                    try_paths = [style_path]

                                applied = False
                                for sp in try_paths:
                                    try:
                                        arcpy.AddMessage(f"  - Checking style candidate: {sp} (exists: {os.path.exists(sp)})")
                                        if not os.path.exists(sp):
                                            continue
                                        # Attempt to swap/import style and re-point to FGDB layer; if that succeeds the style layer becomes final
                                        final_after_style = _apply_style_swap(site_map, final_layer, sp, display_name=short_name)
                                        if final_after_style:
                                            final_layer = final_after_style
                                            applied = True
                                            arcpy.AddMessage(f"  ✓ Applied style from '{sp}' by swapping for '{short_name}'.")
                                            break
                                        else:
                                            # Fallback: apply symbology directly to the FGDB-backed map layer
                                            try:
                                                arcpy.management.ApplySymbologyFromLayer(final_layer, sp)
                                                applied = True
                                                arcpy.AddMessage(f"  ✓ Applied style from '{sp}' using ApplySymbologyFromLayer for '{short_name}'.")
                                                break
                                            except Exception as e_f:
                                                arcpy.AddWarning(f"  - ApplySymbologyFromLayer fallback also failed for '{sp}': {e_f}\n{traceback.format_exc()}")
                                                continue
                                    except Exception:
                                        continue
                                if not applied:
                                    arcpy.AddMessage(f"  - No valid style file found or applied for '{short_name}' (checked {len(try_paths)} locations).")

                            try:
                                _cleanup_duplicates(site_map, final_layer, short_name, preexisting_names=preexisting_layer_names)
                            except Exception:
                                pass

                # end site_map block
            except Exception as e:
                arcpy.AddWarning(f"  - Could not move temporary extract to final location for '{short_name}': {e}\n{traceback.format_exc()}")
                failed.append(short_name)
                try:
                    if arcpy.Exists(tmp_out):
                        arcpy.management.Delete(tmp_out)
                except:
                    pass
                try:
                    arcpy.management.Delete(temp_layer_name)
                except:
                    pass
                if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                    try:
                        arcpy.management.Delete(buffer_fc)
                    except:
                        pass
                continue

            # cleanup per-record temporary items
            try:
                if arcpy.Exists(temp_layer_name):
                    arcpy.management.Delete(temp_layer_name)
                if buffer_fc != study_area_fc and arcpy.Exists(buffer_fc):
                    arcpy.management.Delete(buffer_fc)
            except:
                pass

        # Create SiteLotsReport if a Lots layer was produced
        arcpy.AddMessage("Creating SiteLotsReport table...")
        lots_fc = None
        for po in processed_outputs:
            if "lot" in po["shortname"].lower():
                lots_fc = po["path"]
                break

        if not lots_fc:
            arcpy.AddWarning("Could not find a 'Lots' layer among processed outputs to build SiteLotsReport. Skipping SiteLotsReport.")
        else:
            arcpy.AddMessage(f"  - Using Lots layer at {lots_fc}")
            lots_layer = f"temp_lots_layer_{uuid.uuid4().hex[:6]}"
            try:
                arcpy.management.MakeFeatureLayer(lots_fc, lots_layer)
                arcpy.management.SelectLayerByLocation(lots_layer, "WITHIN", study_area_fc)
                selected_count = int(arcpy.management.GetCount(lots_layer).getOutput(0))
                arcpy.AddMessage(f"  - {selected_count} lots within subject site.")
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

                lot_f = find_field(["lotnumber", "lot_no", "lot"])
                section_f = find_field(["sectionnumber", "section_no", "section"])
                plan_f = find_field(["plannumber", "plan_number", "plan"])
                plan_area_f = find_field(["planlotarea", "plan_lot_area", "planlotarea"])
                plan_area_units_f = find_field(["planlotareaunits", "plan_lot_area_units", "planlotareaunits"])

                insert_fields = ["Lot", "Section", "Plan", "PlanLotArea", "PlanLotAreaUnits"]
                src_field_list = [lot_f, section_f, plan_f, plan_area_f, plan_area_units_f]
                actual_src_fields = [f for f in src_field_list if f]
                if not actual_src_fields:
                    arcpy.AddWarning("No suitable source fields found in Lots layer to build SiteLotsReport; skipping SiteLotsReport.")
                else:
                    with arcpy.da.InsertCursor(report_table, insert_fields) as ins, arcpy.da.SearchCursor(lots_layer, actual_src_fields) as src:
                        for srow in src:
                            out_row = []
                            for fld in [lot_f, section_f, plan_f, plan_area_f, plan_area_units_f]:
                                if fld:
                                    try:
                                        idx = actual_src_fields.index(fld)
                                        val = srow[idx]
                                    except ValueError:
                                        val = None
                                else:
                                    val = None
                                if val is None:
                                    if fld == plan_area_f:
                                        out_row.append(None)
                                    else:
                                        out_row.append('')
                                else:
                                    out_row.append(val)
                            ins.insertRow(out_row)
                arcpy.AddMessage(f"  ✓ SiteLotsReport created: {report_table}")
            except Exception as e:
                arcpy.AddWarning(f"  - Error creating SiteLotsReport: {e}\n{traceback.format_exc()}")
            finally:
                try:
                    if arcpy.Exists(lots_layer):
                        arcpy.management.Delete(lots_layer)
                except:
                    pass

        # Note: PCT report creation has been removed per request.

        # Final summary messages
        arcpy.AddMessage("\nExtraction summary:")
        arcpy.AddMessage(f"  - Extracted new layers: {len(extracted_new)}")
        if extracted_new:
            arcpy.AddMessage(f"    {extracted_new}")
        arcpy.AddMessage(f"  - Replaced (overwritten) layers: {len(replaced)}")
        if replaced:
            arcpy.AddMessage(f"    {replaced}")
        arcpy.AddMessage(f"  - Skipped layers (existing and not requested to refresh): {len(skipped)}")
        if skipped:
            arcpy.AddMessage(f"    {skipped}")
        arcpy.AddMessage(f"  - Failed layers: {len(failed)}")
        if failed:
            arcpy.AddMessage(f"    {failed}")

        if fallback_qurls_for_failed:
            arcpy.AddMessage("\nFallback REST queries used for failed layers (for debugging):")
            for item in fallback_qurls_for_failed:
                arcpy.AddMessage(f"  - Layer: {item.get('shortname')}  |  qurl: {item.get('qurl')}  |  error: {item.get('error')}")
            arcpy.AddMessage("Tip: Copy the qurl into a browser or curl to inspect the service response.")

        # Cleanup of known temporary items in default GDB
        try:
            arcpy.AddMessage("Cleaning up temporary data created during Step 2...")
            prefixes = ("tmp_extract_", "temp_dissolved_", "temp_property_", "tmp_", "temp_")
            prev_ws = arcpy.env.workspace
            arcpy.env.workspace = default_gdb
            fc_list = arcpy.ListFeatureClasses() or []
            for fc in fc_list:
                try:
                    if any(fc.lower().startswith(pref.lower()) for pref in prefixes):
                        full = os.path.join(default_gdb, fc)
                        if any(full == po["path"] for po in processed_outputs):
                            continue
                        try:
                            arcpy.management.Delete(full)
                        except Exception as e_del:
                            arcpy.AddWarning(f"  - Could not delete temp {full}: {e_del}")
                except Exception:
                    pass
            tbls = arcpy.ListTables() or []
            for tbl in tbls:
                try:
                    if any(tbl.lower().startswith(pref.lower()) for pref in prefixes):
                        full = os.path.join(default_gdb, tbl)
                        try:
                            arcpy.management.Delete(full)
                        except Exception as e_del:
                            arcpy.AddWarning(f"  - Could not delete temp {full}: {e_del}")
                except Exception:
                    pass
            try:
                arcpy.env.workspace = prev_ws
            except Exception:
                pass
        except Exception as e:
            arcpy.AddWarning(f"Cleanup during Step 2 encountered errors: {e}\n{traceback.format_exc()}")

        # Funky final summary
        arcpy.AddMessage("\n" + ("✨" * 12))
        arcpy.AddMessage("🌈 FUNKY FINAL REPORT — STEP 2 🌈")
        arcpy.AddMessage("-" * 50)
        arcpy.AddMessage(f"Project: {project_number}")
        arcpy.AddMessage(f"Total reference records attempted: {len(features)}")
        arcpy.AddMessage(f"New extractions: {len(extracted_new)}  |  Replacements: {len(replaced)}  |  Skipped: {len(skipped)}  |  Failed: {len(failed)}")
        arcpy.AddMessage("\nDetailed lists:")
        arcpy.AddMessage(f"  - Extracted: {extracted_new if extracted_new else 'None'}")
        arcpy.AddMessage(f"  - Replaced: {replaced if replaced else 'None'}")
        arcpy.AddMessage(f"  - Skipped: {skipped if skipped else 'None'}")
        arcpy.AddMessage(f"  - Failed: {failed if failed else 'None'}")
        arcpy.AddMessage("-" * 50)
        arcpy.AddMessage(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        arcpy.AddMessage(("✨" * 12) + "\n")
        arcpy.AddMessage("\nSTEP 2 COMPLETE - Standard project layers extracted and reports created.")

        summary["success"] = True
        summary["extracted"] = extracted_new
        summary["replaced"] = replaced
        summary["skipped"] = skipped
        summary["failed"] = failed

    except Exception as e:
        arcpy.AddError(f"Error executing Step 2: {str(e)}\n{traceback.format_exc()}")

    return summary


def _cli():
    """
    CLI entry for testing:
    python ImportStdSiteLayers.py <project_number> [overwrite_flag] [force_requery]
    """
    import sys
    if len(sys.argv) < 2:
        print("Usage: ImportStdSiteLayers.py <project_number> [overwrite_flag] [force_requery]")
        return
    pn = sys.argv[1]
    ow = bool(sys.argv[2]) if len(sys.argv) > 2 else False
    fq = bool(sys.argv[3]) if len(sys.argv) > 3 else False
    res = run_import_std_site_layers(pn, overwrite_flag=ow, force_requery=fq)
    print("Result:", res)


if __name__ == "__main__":
    _cli()
