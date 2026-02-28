#!/usr/bin/env python3
"""Load WU (Weather Underground) sensor calibration coefficients to BigQuery."""

import os

import pandas as pd
from google.cloud import bigquery

PROJECT = os.environ.get("GCP_PROJECT_ID", "durham-weather-466502")

# WU calibration data
wu_calibration = {
    "stationId": [
        "KNCDURHA634",
        "KNCDURHA635",
        "KNCDURHA636",
        "KNCDURHA638",
        "KNCDURHA639",
        "KNCDURHA640",
        "KNCDURHA641",
        "KNCDURHA642",
        "KNCDURHA643",
        "KNCDURHA644",
        "KNCDURHA645",
        "KNCDURHA646",
        "KNCDURHA647",
        "KNCDURHA648",
    ],
    "n_temp_pairs": [
        512,
        510,
        513,
        512,
        512,
        489,
        489,
        488,
        488,
        468,
        466,
        436,
        445,
        444,
    ],
    "a_temp": [
        0.978279969,
        0.998619437,
        1.004338934,
        1.006168202,
        1.002699434,
        1.002576387,
        0.989250027,
        0.99304641,
        1.001016257,
        0.996626104,
        0.992918358,
        0.991343973,
        0.983041313,
        0.961065031,
    ],
    "b_temp": [
        0.555712135,
        0.100682979,
        -0.135705046,
        -0.155417799,
        -0.048202601,
        -0.06704812,
        0.217131245,
        0.179409891,
        -0.026873962,
        0.068579223,
        0.195374654,
        0.219475855,
        0.37616959,
        0.816737012,
    ],
    "n_rh_pairs": [
        512,
        510,
        513,
        512,
        512,
        489,
        489,
        488,
        488,
        468,
        466,
        436,
        445,
        444,
    ],
    "a_rh": [
        1.019700274,
        1.043732577,
        1.004948444,
        1.012557105,
        0.997795744,
        1.002772532,
        0.98079875,
        1.000561676,
        1.002635684,
        0.991928542,
        0.976871593,
        0.999591186,
        0.982427233,
        0.966017833,
    ],
    "b_rh": [
        -3.455721892,
        -3.815822447,
        -0.206125286,
        -0.378601446,
        -0.064067586,
        -0.146825753,
        1.200254129,
        -0.198767175,
        -0.156990166,
        0.921527312,
        1.359513468,
        0.533541471,
        1.722091219,
        2.835630079,
    ],
}

df = pd.DataFrame(wu_calibration)

client = bigquery.Client(project=PROJECT)

# Create table if not exists
schema = [
    bigquery.SchemaField("stationId", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("n_temp_pairs", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("a_temp", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("b_temp", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("n_rh_pairs", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("a_rh", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("b_rh", "FLOAT64", mode="NULLABLE"),
]

table_id = f"{PROJECT}.sensors.wu_calibration_config"

# Truncate and load
job_config = bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE")
job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
job.result()

print(f"✅ Loaded {len(df)} WU calibration records to {table_id}")
print("\nSample:")
print(df.head(3))
