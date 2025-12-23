# 📊 Oura Ring Data Collection Overview

This document outlines all the data types available from the Oura Ring API v2.

---

## 🔍 Available Data Types

Your Oura Ring integration supports **7 primary data types**:

### 1. 💤 **Daily Sleep** (`daily_sleep`)

**Endpoint:** `v2/usercollection/daily_sleep`

Daily sleep summary with aggregated metrics.

**Key Metrics:**

- **Sleep Score** (0-100)
- **Total Sleep Duration** - Total time asleep
- **Sleep Efficiency** - Percentage of time in bed actually sleeping
- **Sleep Latency** - Time to fall asleep
- **Restful Sleep** - Time spent in deep + REM sleep
- **REM Sleep Duration**
- **Deep Sleep Duration**
- **Light Sleep Duration**
- **Awake Time**
- **Sleep Timing** - Bedtime, wake time, midpoint
- **Sleep Regularity** - Consistency of sleep schedule

**Use Cases:**

- Sleep quality analysis
- Circadian rhythm tracking
- Recovery monitoring
- Sleep pattern correlations with environmental data

---

### 2. 🛏️ **Sleep Periods** (`sleep_periods`)

**Endpoint:** `v2/usercollection/sleep`

Detailed sleep session data (can include naps).

**Key Metrics:**

- **Individual Sleep Sessions** - Multiple per day if napping
- **Sleep Stages Timeline** - Minute-by-minute sleep stages
- **Heart Rate During Sleep** - Average, lowest, 5-minute intervals
- **HRV During Sleep** - Heart rate variability
- **Breathing Rate** - Average respirations per minute
- **Body Temperature** - Temperature deviation from baseline
- **Movement Count** - Sleep disruptions

**Use Cases:**

- Detailed sleep architecture analysis
- Nap tracking
- Sleep stage distribution
- Physiological monitoring during sleep

---

### 3. 🏃 **Daily Activity** (`daily_activity`)

**Endpoint:** `v2/usercollection/daily_activity`

Daily movement and activity summary.

**Key Metrics:**

- **Activity Score** (0-100)
- **Steps** - Total daily steps
- **Calories Burned** - Active + resting calories
- **Active Calories** - Calories from movement
- **METs (Metabolic Equivalents)** - Activity intensity
- **Medium Activity Time** - Moderate intensity duration
- **High Activity Time** - Vigorous intensity duration
- **Inactivity Alerts** - Long periods without movement
- **Target Calories** - Personalized daily goal
- **Target Meters** - Distance goals

**Use Cases:**

- Activity level monitoring
- Energy expenditure tracking
- Movement pattern analysis
- Sedentary behavior detection

---

### 4. 🎯 **Daily Readiness** (`daily_readiness`)

**Endpoint:** `v2/usercollection/daily_readiness`

Overall recovery and readiness score.

**Key Metrics:**

- **Readiness Score** (0-100)
- **Temperature Deviation** - From personal baseline
- **Activity Balance** - Recovery vs. activity
- **Body Temperature Trend**
- **HRV Balance** - Heart rate variability trends
- **Previous Night's Sleep** - Sleep quality impact
- **Previous Day's Activity** - Activity load impact
- **Recovery Index** - Overall recovery state
- **Resting Heart Rate** - Compared to baseline

**Use Cases:**

- Recovery monitoring
- Training load management
- Illness detection (temperature changes)
- Stress assessment

---

### 5. ❤️ **Heart Rate** (`heart_rate`)

**Endpoint:** `v2/usercollection/heartrate`

High-resolution heart rate data (5-minute intervals).

**Key Metrics:**

- **5-Minute Interval Data** - Heart rate every 5 minutes
- **Timestamp** - Precise timing for each reading
- **Source** - Sleep, awake, workout, etc.
- **Continuous Monitoring** - 24/7 tracking

**Use Cases:**

- Cardiovascular health monitoring
- Stress response tracking
- Real-time heart rate analysis
- Heart rate variability calculations
- Environmental correlation (e.g., air quality impact on HR)

---

### 6. 🧘 **Sessions** (`sessions`)

**Endpoint:** `v2/usercollection/session`

Guided sessions and relaxation activities.

**Key Metrics:**

- **Session Type** - Meditation, breathing, etc.
- **Duration** - Length of session
- **Heart Rate During Session**
- **HRV During Session**
- **Mood** - Pre/post session mood
- **Mood Improvement** - Session effectiveness

**Use Cases:**

- Meditation tracking
- Stress management analysis
- Breathing exercise monitoring
- Mental health insights

---

### 7. 💪 **Workouts** (`workouts`)

**Endpoint:** `v2/usercollection/workout`

Exercise and training sessions.

**Key Metrics:**

- **Workout Type** - Running, cycling, walking, etc.
- **Duration** - Total workout time
- **Intensity** - Easy, moderate, hard
- **Calories Burned**
- **Average Heart Rate**
- **Max Heart Rate**
- **Heart Rate Zones** - Time in each HR zone
- **Distance** - For applicable activities
- **Source** - Manual entry or detected

**Use Cases:**

- Exercise tracking
- Training load monitoring
- Performance analysis
- Recovery planning

---

## 📅 Data Collection Configuration

Default settings in `oura_import_options.py`:

```python
DATA_TYPES = {
    "daily_sleep": True,        # ✓ Enabled
    "sleep_periods": True,      # ✓ Enabled
    "daily_activity": True,     # ✓ Enabled
    "daily_readiness": True,    # ✓ Enabled
    "heart_rate": True,         # ✓ Enabled
    "sessions": True,           # ✓ Enabled
    "workouts": True,           # ✓ Enabled
}
```

**To disable specific data types**, set them to `False` in the config.

---

## 🔗 Data Integration

### Current Implementation:

- ✅ **Local Storage** - JSON files + CSV summaries
- ✅ **BigQuery Export** - Optional cloud storage
- ✅ **13 Residents** - Multi-user support
- ✅ **Date Range Queries** - Flexible time periods

### Available Endpoints:

| Data Type       | Method                  | Granularity     | Typical Use             |
| --------------- | ----------------------- | --------------- | ----------------------- |
| Daily Sleep     | `get_daily_sleep()`     | 1 per day       | Sleep quality trends    |
| Sleep Periods   | `get_sleep_periods()`   | Multiple/day    | Detailed sleep analysis |
| Daily Activity  | `get_daily_activity()`  | 1 per day       | Movement patterns       |
| Daily Readiness | `get_daily_readiness()` | 1 per day       | Recovery tracking       |
| Heart Rate      | `get_heart_rate()`      | 5-min intervals | Continuous monitoring   |
| Sessions        | `get_sessions()`        | Per session     | Meditation/breathing    |
| Workouts        | `get_workouts()`        | Per workout     | Exercise tracking       |

---

## 🎯 Research & Analysis Opportunities

### Environmental Correlations:

- **Air Quality ↔ Sleep Quality** - PM2.5 impact on deep sleep
- **Temperature ↔ HRV** - Climate effects on recovery
- **Humidity ↔ Breathing Rate** - Environmental stress
- **Noise Levels ↔ Sleep Disruption** - Urban environment impact

### Health Monitoring:

- **Circadian Rhythm Analysis** - Sleep timing consistency
- **Recovery Patterns** - Training load vs. readiness
- **Stress Detection** - HRV + temperature changes
- **Illness Prediction** - Temperature + RHR elevation

### Population Health:

- **13 Residents** - Community health trends
- **Seasonal Variations** - Climate impact on health
- **Activity Patterns** - Movement behavior analysis
- **Sleep Equity** - Environmental justice implications

---

## 📊 Data Volume Estimates

**Per Resident:**

- **Daily Sleep:** ~1 record/day (~365/year)
- **Sleep Periods:** ~1-3 records/day (~500/year)
- **Daily Activity:** ~1 record/day (~365/year)
- **Daily Readiness:** ~1 record/day (~365/year)
- **Heart Rate:** ~288 records/day (~105,000/year) ⚠️ HIGH VOLUME
- **Sessions:** ~0-5 records/day (variable)
- **Workouts:** ~0-3 records/day (variable)

**For 13 Residents:**

- **Heart Rate Data:** ~1.4 million records/year
- **Daily Metrics:** ~15,000 records/year combined
- **Total:** ~1.5 million records/year

💡 **Storage Recommendation:** Use BigQuery for heart rate data, local JSON for daily summaries.

---

## 🚀 Getting Started

### Test Data Collection:

```bash
# Test connection (already confirmed working ✅)
.venv/bin/python test_oura_connection.py

# Collect all data types for one resident
.venv/bin/python -m oura-rings.cli --residents 1 --start 2025-11-01 --end 2025-11-07

# Collect specific data type
# Edit DATA_TYPES in oura_import_options.py to enable/disable types
```

### Configuration:

Edit `oura-rings/oura_import_options.py`:

```python
RESIDENTS_TO_PROCESS = [1, 2, 3]  # Select residents
DATE_CONFIG = {
    "start_date": "2025-01-01",
    "end_date": "2025-11-07"
}
DATA_TYPES = {
    "daily_sleep": True,     # Enable/disable as needed
    "heart_rate": False,     # Disable if too much data
    # ...
}
```

---

## 📚 Additional Resources

- **Oura API Documentation:** https://cloud.ouraring.com/v2/docs
- **Data Dictionary:** Available in collected JSON files
- **BigQuery Schema:** Auto-generated from data structure
- **Research Applications:** See environmental correlation studies

---

**Next Step:**

Configure `RESIDENTS_TO_PROCESS` and date ranges

For questions or issues, see `oura-rings/README.md` or `SECRETS_SETUP.md`.
