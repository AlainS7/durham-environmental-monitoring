# Project Backlog

## Calibration Fixes & Improvements

### [COMPLETED] Update WU Calibration Coefficients for KNCDURHA646

**Date**: February 19, 2026
**Status**: ✅ COMPLETED
**Branch**: feat/parquet-schema-fix

**Issue**: Station KNCDURHA646 had incorrect calibration coefficients (likely from earlier testing data).

**Old Values**:

```
stationId:        KNCDURHA646
n_temp_pairs:     466
a_temp:           1.01142757
b_temp:           -0.356295383
n_rh_pairs:       466
a_rh:             0.925362568
b_rh:             6.935959161
reference_method: (not tracked)
```

**New Values** (validated by median method):

```
stationId:        KNCDURHA646
n_temp_pairs:     436
a_temp:           0.991343973
b_temp:           0.219475855
n_rh_pairs:       436
a_rh:             0.999591186
b_rh:             0.533541471
reference_method: median
```

**Changes Made**:

1. Updated `scripts/load_wu_calibration.py` - calibration coefficients table
   - Changed n_temp_pairs: 466 → 436
   - Changed a_temp: 1.01142757 → 0.991343973
   - Changed b_temp: -0.356295383 → 0.219475855
   - Changed n_rh_pairs: 466 → 436
   - Changed a_rh: 0.925362568 → 0.999591186
   - Changed b_rh: 6.935959161 → 0.533541471

**Files Modified**:

- `scripts/load_wu_calibration.py`

**Next Steps**:

1. Run script to reload calibration config: `python3 scripts/load_wu_calibration.py`
2. Backfill transformation for any dates using old coefficients:
   ```bash
   python scripts/run_transformations_batch.sh 2025-07-04 2026-02-12
   ```
3. Sync updated data to Grafana: `python3 scripts/sync_to_grafana.py`

**Impact**:

- Affects calibrated temperature and humidity metrics (temperature_calibrated, humidity_calibrated)
- WU station KNCDURHA646 will now have more accurate calibrated readings
- Historical data will be recalculated with new coefficients

---

## Data Quality Improvements (Future)

- [ ] Add validation script to verify calibration coefficient ranges (a: 0.8-1.2, b: ±5)
- [ ] Document reference method (median/mean) in wu_calibration_config table schema
- [ ] Create dashboard panel showing raw vs calibrated WU metrics side-by-side
- [ ] Set up alerts if coefficient values seem unreasonable

---

## Pipeline Enhancements (Future)

- [ ] Add audit table tracking calibration coefficient changes with timestamps
- [ ] Implement version control for calibration_config (with effective_date tracking)
- [ ] Create monthly calibration coefficient validation report

---

## Known Issues

None currently tracked.
