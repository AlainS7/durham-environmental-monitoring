import json
from scripts.check_row_thresholds import load_thresholds, DEFAULT_THRESHOLDS

def test_load_thresholds_yaml_overrides(tmp_path, monkeypatch):
    # create YAML config overriding one value and adding new table
    yaml_content = """
row_thresholds:
  wu_raw_materialized: 5
  new_table: 7
""".strip()
    cfg = tmp_path / 'data_quality.yaml'
    cfg.write_text(yaml_content)
    # run loader
    thresholds = load_thresholds(str(cfg), None)
    assert thresholds['wu_raw_materialized'] == 5
    assert thresholds['new_table'] == 7
    # untouched default preserved
    assert thresholds['tsi_raw_materialized'] == DEFAULT_THRESHOLDS['tsi_raw_materialized']

def test_load_thresholds_json_precedence(tmp_path):
    # YAML sets value to 10, JSON should override to 3
    yaml_content = """
row_thresholds:
  wu_raw_materialized: 10
""".strip()
    cfg = tmp_path / 'data_quality.yaml'
    cfg.write_text(yaml_content)
    json_override = tmp_path / 'override.json'
    json_override.write_text(json.dumps({'wu_raw_materialized': 3}))
    thresholds = load_thresholds(str(cfg), str(json_override))
    assert thresholds['wu_raw_materialized'] == 3

def test_load_thresholds_missing_yaml(monkeypatch):
    # no file, should just return defaults
    thresholds = load_thresholds('nonexistent.yaml', None)
    for k,v in DEFAULT_THRESHOLDS.items():
        assert thresholds[k] == v
