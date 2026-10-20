"""箱规库、实测导入和发货/实测对比。"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from fba_tool.carton_store import (
    CartonValidationError,
    DbNewerError,
    active_specs,
    apply_import,
    archive_spec,
    assign_measurement,
    compare_carton,
    compare_export_xlsx,
    compare_items,
    create_measured_average,
    create_spec,
    delete_import_batch,
    export_specs_csv,
    export_specs_xlsx,
    history_for,
    list_specs,
    preview_import,
    record_box_snapshot,
    replace_spec,
    set_default,
)
from fba_tool.measurement_adapters import ParseError, detect_adapter
from fba_tool.carton_store import import_measurements

router = APIRouter()


def _guard(fn):
    try:
        return fn()
    except DbNewerError as exc:
        raise HTTPException(status_code=409, detail={"code": "DB_NEWER_THAN_APP", "message": str(exc)}) from exc
    except CartonValidationError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc), "fields": exc.fields}) from exc
    except ParseError as exc:
        raise HTTPException(status_code=422, detail={"message": exc.message}) from exc


@router.get("/api/carton-specs")
def api_list_specs(sku: str = ""):
    return _guard(lambda: {"items": list_specs(sku)})


@router.get("/api/carton-specs/{sku}/history")
def api_spec_history(sku: str):
    return _guard(lambda: {"items": history_for(sku)})


@router.post("/api/carton-specs")
def api_create_spec(body: dict):
    return _guard(lambda: create_spec(body))


@router.patch("/api/carton-specs/{spec_id}")
def api_patch_spec(spec_id: int, body: dict):
    return _guard(lambda: replace_spec(spec_id, body))


@router.post("/api/carton-specs/{spec_id}/set-default")
def api_set_default(spec_id: int):
    return _guard(lambda: set_default(spec_id))


@router.post("/api/carton-specs/{spec_id}/archive")
def api_archive(spec_id: int):
    return _guard(lambda: archive_spec(spec_id))


@router.get("/api/carton-specs/sku/{sku}")
def api_specs_for_sku(sku: str):
    return _guard(lambda: {"items": active_specs(sku)})


@router.post("/api/carton-specs/import/preview")
async def api_import_preview(file: UploadFile = File(...)):
    data = await file.read()
    from fba_tool.carton_import import parse_carton_spec_rows

    def run():
        records, errors = parse_carton_spec_rows(data, file.filename or "")
        preview = preview_import(records)
        preview["errors"] = errors + preview["errors"]
        return preview

    return _guard(run)


@router.post("/api/carton-specs/import/apply")
async def api_import_apply(file: UploadFile = File(...)):
    data = await file.read()
    from fba_tool.carton_import import parse_carton_spec_rows

    def run():
        records, errors = parse_carton_spec_rows(data, file.filename or "")
        if errors:
            raise CartonValidationError({"file": "；".join(item["message"] for item in errors[:5])})
        return apply_import(records, file.filename or "")

    return _guard(run)


@router.get("/api/carton-specs/export.xlsx")
def api_export_xlsx():
    body = _guard(export_specs_xlsx)
    return Response(content=body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/api/carton-specs/export.csv")
def api_export_csv():
    body = _guard(export_specs_csv)
    return Response(content=body, media_type="text/csv")


@router.post("/api/shipments/{fba_id}/box-snapshot")
def api_box_snapshot(fba_id: str, body: dict):
    return _guard(lambda: record_box_snapshot(
        fba_id,
        str(body.get("stage") or "sta_export"),
        list(body.get("boxes") or []),
        task_id=str(body.get("task_id") or ""),
        batch=str(body.get("batch") or ""),
    ))


@router.post("/api/measurements/import/preview")
async def api_measure_preview(file: UploadFile = File(...)):
    data = await file.read()

    def run():
        adapter = detect_adapter(file.filename or "", data)
        rows = adapter.parse(data)
        return {"adapter": adapter.name, "rows": len(rows), "preview": rows[:20]}

    return _guard(run)


@router.post("/api/measurements/import/apply")
async def api_measure_apply(file: UploadFile = File(...)):
    data = await file.read()

    def run():
        adapter = detect_adapter(file.filename or "", data)
        rows = adapter.parse(data)
        measured_by = "forwarder_jiufang"
        if adapter.name == "send_box_xlsx":
            measured_by = "forwarder_send"
        elif adapter.name == "manual_xlsx":
            measured_by = "manual"
        elif adapter.name == "fee_preview_txt":
            measured_by = "fee_preview"
        return import_measurements(rows, measured_by=measured_by, source_file=file.filename or adapter.name)

    return _guard(run)


@router.delete("/api/measurements/import/{batch_id}")
def api_measure_delete(batch_id: str):
    return _guard(lambda: delete_import_batch(batch_id))


@router.post("/api/measurements/{measurement_id}/assign")
def api_assign(measurement_id: int, body: dict):
    return _guard(lambda: assign_measurement(measurement_id, str(body.get("fba_box_id") or "")))


@router.get("/api/carton-compare")
def api_compare(fba_id: str = "", batch: str = "", source: str = "", threshold: float | None = None):
    return _guard(lambda: compare_carton(fba_id, batch, source, threshold))


@router.get("/api/carton-compare/export.xlsx")
def api_compare_export(fba_id: str = "", batch: str = "", source: str = ""):
    body = _guard(lambda: compare_export_xlsx(fba_id, batch, source))
    return Response(content=body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/api/item-compare")
def api_item_compare(batch: str = "", marketplace: str = "US"):
    return _guard(lambda: compare_items(batch, marketplace))


@router.post("/api/carton-specs/from-measure")
def api_from_measure(body: dict):
    return _guard(lambda: create_measured_average(
        str(body.get("sku") or ""),
        [body.get("length_cm"), body.get("width_cm"), body.get("height_cm")],
        body.get("gross_kg"),
        int(body.get("qty_per_carton") or 0),
        str(body.get("spec_name") or ""),
    ))


@router.get("/api/data-dir/status")
def api_data_dir_status():
    from fba_tool.app_paths import legacy_import_status

    return legacy_import_status()


@router.post("/api/data-dir/import-legacy")
def api_import_legacy():
    from fba_tool.app_paths import import_legacy_data_dir

    return _guard(import_legacy_data_dir)


@router.post("/api/app-data/backup-zip")
def api_backup_zip():
    from pathlib import Path
    from tempfile import NamedTemporaryFile

    from fba_tool.carton_store import zip_app_data

    def run():
        with NamedTemporaryFile(suffix=".zip", delete=False) as handle:
            path = Path(handle.name)
        zip_app_data(path)
        body = path.read_bytes()
        path.unlink(missing_ok=True)
        return body

    body = _guard(run)
    return Response(content=body, media_type="application/zip")
