import importlib.util
import pathlib

SCRIPT_PATH = pathlib.Path("scripts/ingest_nifc_fire_perimeters.py")

spec = importlib.util.spec_from_file_location("ingest_nifc_fire_perimeters", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)  # type: ignore
mod = module


def test_normalize_incident_id_strips_braces_and_uppercases():
    assert mod._normalize_incident_id("  {abc-123} ") == "ABC-123"
    assert mod._normalize_incident_id(None) is None


def test_build_rows_deduplicates_identical_feature_payloads():
    feature = {
        "properties": {
            "OBJECTID": 101,
            "attr_IrwinID": "{abc-123}",
            "attr_ModifiedOnDateTime_dt": 1_736_124_000_000,
            "poly_IncidentName": "Sample Fire",
            "attr_PercentContained": "45",
            "attr_IncidentSize": "130.2",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-79.0, 35.0], [-79.1, 35.0], [-79.0, 35.1], [-79.0, 35.0]]],
        },
    }

    rows = mod.build_rows(
        features=[feature, feature],
        layer_url="https://example.com/layer",
        ingest_iso="2026-05-07T00:00:00.000000Z",
    )

    assert len(rows) == 1
    assert rows[0]["incident_id"] == "ABC-123"
    assert rows[0]["source_object_id"] == 101


def test_build_merge_raw_sql_uses_record_hash_dedup():
    sql = mod.build_merge_raw_sql("proj", "dataset", "proj.dataset._tmp_nifc")

    assert "MERGE `proj.dataset.nifc_fire_perimeters_raw` T" in sql
    assert "USING `proj.dataset._tmp_nifc` S" in sql
    assert "ON T.record_hash = S.record_hash" in sql


def test_build_merge_current_sql_uses_latest_per_incident():
    sql = mod.build_merge_current_sql("proj", "dataset", "proj.dataset._tmp_nifc")

    assert "MERGE `proj.dataset.nifc_fire_perimeters_current` T" in sql
    assert "ROW_NUMBER() OVER (" in sql
    assert "PARTITION BY incident_id" in sql
    assert "ORDER BY source_modified_at DESC NULLS LAST, ingest_ts DESC" in sql
    assert "WHEN MATCHED AND (" in sql
