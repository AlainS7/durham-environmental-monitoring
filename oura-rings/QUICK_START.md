# 🚀 QUICK START: Using the Updated BigQuery Pipeline

## ✅ What's New

Added **3 NEW data types** to BigQuery pipeline:

- **SpO2** - Blood oxygen levels
- **Stress** - Stress/recovery metrics
- **Cardiovascular Age** - Vascular health

## 📋 Quick Test

### 1. Test Collection (No Upload)

```bash
.venv/bin/python test_bigquery_pipeline.py
```

**Expected:** Shows data collection + DataFrame building for all 6 tables

### 2. Test with Dry-Run (Safe)

```bash
# Enable in config first:
# OPTIONS["export_to_bigquery"] = True
# OPTIONS["bq_dry_run"] = True

.venv/bin/python -m oura-rings.cli --residents 1 --export-bq
```

**Expected:** Logs "would upload X rows" without actual upload

### 3. Real Upload (One Resident)

```bash
# Set env vars
export BQ_PROJECT="durham-weather-466502"
export BQ_LOCATION="US"

# Enable real upload:
# OPTIONS["bq_dry_run"] = False

.venv/bin/python -m oura-rings.cli --residents 1 --export-bq --no-dry-run
```

**Expected:** Creates tables in BigQuery dataset "oura"

### 4. Production Run (All Residents)

```bash
.venv/bin/python -m oura-rings.cli \
  --residents 1 2 3 \
  --start 2025-01-01 \
  --end 2025-11-07 \
  --export-bq \
  --no-dry-run
```

## 🔍 Verify in BigQuery

```sql
-- Check tables exist
SELECT table_name, row_count
FROM oura.__TABLES__;

-- View SpO2 data
SELECT * FROM oura.oura_daily_spo2 LIMIT 10;

-- View Stress data
SELECT * FROM oura.oura_daily_stress LIMIT 10;

-- View Cardiovascular Age
SELECT * FROM oura.oura_daily_cardiovascular_age LIMIT 10;

-- Quick correlation test
SELECT
  s.day,
  s.spo2_average,
  st.stress_high / 3600.0 as stress_hours
FROM oura.oura_daily_spo2 s
JOIN oura.oura_daily_stress st ON s.day = st.day AND s.resident = st.resident
ORDER BY s.day DESC;
```

## 📊 Expected Tables

```
oura dataset:
├── oura_daily_sleep                    (existing)
├── oura_daily_activity                 (existing)
├── oura_daily_readiness                (existing)
├── oura_daily_spo2                     (NEW!)
├── oura_daily_stress                   (NEW!)
└── oura_daily_cardiovascular_age       (NEW!)
```

## ⚠️ Troubleshooting

### "No module named 'google.cloud'"

```bash
pip install google-cloud-bigquery
```

### "Permission denied"

```bash
# Authenticate with gcloud
gcloud auth application-default login
```

### "Table not found"

- Check dataset exists: `bq ls oura`
- Create if needed: `bq mk --dataset oura`

## 🎯 Files Changed

- ✅ `oura-rings/oura_collector.py` - Collection logic
- ✅ `oura-rings/oura_bigquery_loader.py` - BigQuery frames
- ✅ `test_bigquery_pipeline.py` - Test script

## 📚 Documentation

- Full details: `oura-rings/BIGQUERY_UPDATE_COMPLETE.md`
- Analysis: `oura-rings/BIGQUERY_PIPELINE_ANALYSIS.md`
- New data types: `oura-rings/NEW_DATA_TYPES_FOUND.md`

---
