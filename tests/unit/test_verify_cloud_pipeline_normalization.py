from scripts.verify_cloud_pipeline import _needs_norm_check


def test_needs_norm_check_ignores_legacy_date_suffixed_tables():
    assert _needs_norm_check("staging_wu_20260410") is False
    assert _needs_norm_check("tmp_wu_20250101") is False


def test_needs_norm_check_only_targets_active_staging_tmp_tables():
    assert _needs_norm_check("staging_wu_raw") is True
    assert _needs_norm_check("tmp_wu_normalized") is True
    assert _needs_norm_check("tmp_unpivot_wu") is False
    assert _needs_norm_check("snapshot_wu_daily") is False
    assert _needs_norm_check("view_wu_latest") is False
