from unittest.mock import patch, MagicMock
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from google.cloud.exceptions import NotFound

# Dynamically load the oura_bigquery_loader module (folder name has a hyphen)
ROOT = Path(__file__).resolve().parents[2]
LOADER_PATH = ROOT / "oura-rings" / "oura_bigquery_loader.py"
spec = spec_from_file_location("oura_bigquery_loader", str(LOADER_PATH))
assert spec is not None and spec.loader is not None
mod = module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(mod)  # type: ignore

build_daily_frames = mod.build_daily_frames
upload_frames_to_bigquery = mod.upload_frames_to_bigquery

SAMPLE_DATA = {
    "sleep": [
        {
            "day": "2025-10-01",
            "score": 85,
            "contributors": {"efficiency": 90, "deep_sleep": 70},
        }
    ],
    "activity": [
        {
            "day": "2025-10-01",
            "score": 72,
            "contributors": {"move_every_hour": 100, "recovery_time": 80},
        }
    ],
    "readiness": [
        {
            "day": "2025-10-01",
            "score": 79,
            "contributors": {"resting_hr": 60, "hrv_balance": 55},
        }
    ],
}


def test_build_daily_frames_basic():
    frames = build_daily_frames(SAMPLE_DATA, resident_no=3)
    assert set(frames.keys()) == {"daily_sleep", "daily_activity", "daily_readiness"}
    for name, df in frames.items():
        assert not df.empty
        assert "resident" in df.columns
        assert df.loc[0, "resident"] == 3
        assert "day" in df.columns


@patch("google.cloud.bigquery.Client")
def test_upload_frames_dry_run(mock_client):
    frames = build_daily_frames(SAMPLE_DATA, resident_no=1)
    result = upload_frames_to_bigquery(
        frames, dataset="oura", table_prefix="oura", dry_run=True
    )
    assert "tables" in result and "cost_metrics" in result
    tables = result["tables"]
    assert set(tables.keys()) == {
        "oura_daily_sleep",
        "oura_daily_activity",
        "oura_daily_readiness",
    }
    # Ensure no client was constructed in dry run
    mock_client.assert_not_called()


@patch("google.cloud.bigquery.Client")
def test_upload_frames_real(mock_client):
    # Set up fake client and job
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.project = "demo-project"
    mock_instance.get_dataset.side_effect = NotFound("Dataset not found")
    mock_instance.create_dataset.return_value = True
    mock_job = MagicMock()
    mock_job.result.return_value = None
    mock_instance.load_table_from_dataframe.return_value = mock_job

    frames = build_daily_frames(SAMPLE_DATA, resident_no=2)
    result = upload_frames_to_bigquery(
        frames, dataset="oura", table_prefix="oura", dry_run=False
    )
    assert "tables" in result and "cost_metrics" in result
    for v in result["tables"].values():
        assert isinstance(v, int) and v >= 1
    mock_client.assert_called_once()
    assert mock_instance.load_table_from_dataframe.call_count == 3
