import pandas as pd

from src.storage.gcs_uploader import coerce_numeric_columns, TSI_NUMERIC_COLS


def test_coerce_numeric_columns_casts_to_float_and_preserves_nan():
    df = pd.DataFrame(
        {
            "pm2_5": [1, "2", None, "bad"],
            "temperature": [20, 21.5, "22", ""],
            "native_sensor_id": ["a", "b", "c", "d"],
        }
    )

    out = coerce_numeric_columns(df, {"pm2_5", "temperature"})

    assert out["pm2_5"].dtype == "float64"
    assert out["temperature"].dtype == "float64"
    # to_numeric(errors='coerce') turns bad strings into NaN
    assert pd.isna(out["pm2_5"].iloc[3])
    # Non-numeric column untouched
    assert out["native_sensor_id"].equals(df["native_sensor_id"])


def test_tsi_numeric_columns_subset_present_are_coerced():
    df = pd.DataFrame(
        {"pm1_0": [1], "pm2_5": ["3"], "voc_mgm3": ["4.5"], "native_sensor_id": ["x"]}
    )

    out = coerce_numeric_columns(df, TSI_NUMERIC_COLS)

    assert out["pm1_0"].dtype == "float64"
    assert out["pm2_5"].dtype == "float64"
    assert out["voc_mgm3"].dtype == "float64"
    assert out["native_sensor_id"].dtype == df["native_sensor_id"].dtype
