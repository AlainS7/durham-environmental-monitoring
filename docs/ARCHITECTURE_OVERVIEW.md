# Project Architecture Overview

## Current State (Before Enhancement)

```
┌─────────────────────────────────────────────────────────────┐
│              Durham Environmental Monitoring                │
│                   (Current System)                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Data Collection (Python/pandas)                            │
│    ├─ Weather Underground API                               │
│    ├─ TSI Air Quality Sensors                               │
│    └─ Oura Ring Biometric Data                              │
│           ↓                                                 │
│  Processing (CPU - pandas)                                  │
│    ├─ Data Cleaning (~5 min for 100K rows)                 │
│    ├─ Transformations                                       │
│    └─ Aggregations                                          │
│           ↓                                                 │
│  Storage                                                    │
│    ├─ Google Cloud Storage (Parquet)                        │
│    └─ BigQuery (Analytics)                                  │
│           ↓                                                 │
│  Visualization                                              │
│    └─ Looker Studio Dashboards                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘

⚠️  Limitations:
  - Slow processing (5+ minutes for daily data)
  - No ML predictions
  - No real-time capabilities
  - Basic visualizations only
```

## Future State (After Enhancement)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Weather-Health Intelligence Platform - Aquila             │
│              GPU-Accelerated ML-Powered Analytics                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────┐
│  PHASE 1: GPU Data Pipeline  │
│      (RAPIDS cuDF)           │
└───────────┬──────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────┐
│  Data Collection                                             │
│    ├─ Weather Underground API                                │
│    ├─ TSI Air Quality Sensors                                │
│    └─ Oura Ring Biometrics                                   │
└───────────┬──────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────┐
│  GPU-Accelerated Processing (20x faster!) 🚀                 │
│                                                             │
│  ┌────────────────────────────────────────────────────┐     │
│  │  RAPIDS cuDF                                       │     │
│  │    • Data loading: 10x faster                      │     │
│  │    • Cleaning: 15x faster                          │     │
│  │    • Feature engineering: 30x faster               │     │
│  │    • Time: ~15 seconds (was 5 minutes!)            │     │
│  └────────────────────────────────────────────────────┘     │
│                                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  cuML Preprocessing                                │     │
│  │    • GPU-accelerated scaling                       │     │
│  │    • PCA dimensionality reduction                  │     │
│  │    • Outlier detection                             │     │
│  └────────────────────────────────────────────────────┘     │
└───────────┬──────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────┐
│  PHASE 2: ML Predictions     │
│    (TensorRT + C++)          │
└───────────┬──────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────┐
│  Time-Series Model Training                                  │
│                                                              │
│  Input Features:                                             │
│    • Temperature, Humidity, PM2.5, PM10                      │
│    • HRV, Sleep Score, Readiness                             │
│    • Time features, Historical trends                        │
│                                                              │
│  Model Architectures (PyTorch):                              │
│    ├─ LSTM Baseline                                          │
│    ├─ Temporal Fusion Transformer                            │
│    └─ TCN (Temporal Convolutional Network)                   │
│                                                              │
│  Target: Next-day health/air quality prediction              │
└───────────┬──────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────┐
│  TensorRT Optimization Pipeline                              │
│                                                              │
│  PyTorch Model                                               │
│      ↓  (export)                                            │
│  ONNX Format                                                 │
│      ↓  (optimize)                                          │
│  TensorRT Engine                                             │
│      • INT8 Quantization                                     │
│      • Layer Fusion                                          │
│      • Kernel Auto-tuning                                    │
│                                                              │
│  Result: 10-25x faster inference! ⚡                         │
└───────────┬──────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────┐
│  Aquila C++ Inference Engine (<5ms latency)                │
│                                                              │
│  ┌────────────┐   ┌──────────────┐   ┌────────────┐        │
│  │ REST API   │ → │ Preprocessing│ → │ TensorRT   │        │
│  │ (Crow)     │   │  (C++)       │   │  Runtime   │        │
│  └────────────┘   └──────────────┘   └─────┬──────┘        │
│                                             ↓               │
│                                      ┌────────────┐         │
│                                      │Post-process│         │
│                                      │& Response  │         │
│                                      └────────────┘         │
│                                                              │
│  Endpoints:                                                  │
│    • POST /predict   - Get predictions                       │
│    • GET  /health    - Health check                          │
│    • GET  /metrics   - Prometheus metrics                    │
└───────────┬──────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────┐
│  PHASE 3: Full-Stack App     │
│   (FastAPI + React)          │
└───────────┬──────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────┐
│  Backend API (FastAPI)                                       │
│                                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Endpoints:                                        │     │
│  │    • POST /api/v1/predict                          │     │
│  │      └─→ Calls Aquila for ML predictions           │     │
│  │    • GET  /api/v1/sensors/{id}/readings            │     │
│  │      └─→ Fetches from BigQuery                     │     │
│  │    • GET  /api/v1/correlations                     │     │
│  │      └─→ Environmental-Biometric analysis          │     │
│  │    • GET  /api/v1/insights                         │     │
│  │      └─→ AI-generated recommendations              │     │
│  │    • WS   /ws/live                                 │     │
│  │      └─→ Real-time sensor data stream              │     │
│  └────────────────────────────────────────────────────┘     │
│                                                              │
│  Features:                                                   │
│    • JWT Authentication                                      │
│    • Rate Limiting                                           │
│    • Redis Caching                                           │
│    • Request Validation                                      │
└───────────┬──────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────┐
│  Frontend Dashboard (React + TypeScript)                     │
│                                                              │
│  ┌──────────────────────┐  ┌──────────────────────┐         │
│  │  Interactive Map     │  │ Real-Time Predictions │         │
│  │  (Mapbox/Leaflet)    │  │   • Current AQI       │         │
│  │                      │  │   • Health Score      │         │
│  │  📍 Sensor Locations │  │   • Recommendations   │         │
│  └──────────────────────┘  └──────────────────────┘         │
│                                                              │
│  ┌──────────────────────┐  ┌──────────────────────┐         │
│  │ Correlation Charts   │  │ Performance Metrics   │         │
│  │   • Env vs Health    │  │   • Inference Latency │         │
│  │   • Trend Analysis   │  │   • GPU Utilization   │         │
│  │   • Heatmaps         │  │   • Prediction Accuracy│        │
│  └──────────────────────┘  └──────────────────────┘         │
└───────────┬──────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────┐
│  Observability & Monitoring                                  │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │ Structured Logs │  │ Distributed     │  │ Metrics     │ │
│  │ (JSON)          │  │ Tracing         │  │ (Prometheus)│ │
│  │   • Request ID  │  │ (OpenTelemetry) │  │   • Latency │ │
│  │   • Trace ID    │  │   • Spans       │  │   • Errors  │ │
│  │   • Timestamps  │  │   • Context     │  │   • GPU     │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
│                              ↓                               │
│                    ┌──────────────────┐                      │
│                    │ Grafana Dashboard│                      │
│                    │   • System Health│                      │
│                    │   • Performance  │                      │
│                    │   • Alerts       │                      │
│                    └──────────────────┘                      │
└──────────────────────────────────────────────────────────────┘

✅ Benefits:
  ✓ 20-50x faster data processing
  ✓ <5ms prediction latency
  ✓ Real-time insights
  ✓ Production-grade reliability
  ✓ Full observability
  ✓ Impressive portfolio showcase!
```

## Technology Stack

### Phase 1: GPU Acceleration

- **NVIDIA RAPIDS** (cuDF, cuML, cuGraph)
- **CuPy** - GPU-accelerated NumPy
- **Python 3.10+**

### Phase 2: ML & Inference

- **PyTorch 2.0+** - Model training
- **ONNX** - Model interchange format
- **TensorRT 8.6+** - Inference optimization
- **C++17** - High-performance inference engine
- **CMake** - Build system
- **Crow** - REST API framework

### Phase 3: Full-Stack

- **FastAPI** - Python backend
- **React + TypeScript** - Frontend
- **Redis** - Caching layer
- **OpenTelemetry** - Observability
- **Prometheus + Grafana** - Metrics & monitoring
- **Docker + K8s** - Containerization & orchestration

## Performance Comparison

| Operation          | Current (CPU) | Phase 1 (GPU) | Phase 2 (TensorRT) | Improvement |
| ------------------ | ------------- | ------------- | ------------------ | ----------- |
| Data Loading       | 5.0s          | 0.5s          | N/A                | **10x**     |
| Cleaning           | 10.0s         | 0.5s          | N/A                | **20x**     |
| Features           | 30.0s         | 1.0s          | N/A                | **30x**     |
| ML Training        | 2 hours       | 30 min        | N/A                | **4x**      |
| Inference          | N/A (no ML)   | 50ms (Python) | <5ms (C++)         | **10x+**    |
| **Total Pipeline** | **5+ min**    | **<15s**      | **<5ms**           | **20-50x**  |

## Impact Metrics

### Technical Achievement

- **Code Quality**: Production-grade, tested, documented
- **Performance**: Order-of-magnitude improvements
- **Scale**: Handle 100K+ rows, 1000+ req/s
- **Reliability**: 99.9% uptime target

### Project Impact

- **New**: GPU, ML, Systems, Full-Stack
- **Showcase**: Live demo + metrics

## File Structure (After Enhancement)

```
durham-environmental-monitoring/
├── src/
│   ├── data_collection/          # Original pandas pipeline
│   ├── rapids_pipeline/           # NEW: GPU-accelerated pipeline
│   │   ├── __init__.py
│   │   ├── gpu_utils.py
│   │   ├── rapids_data_collector.py
│   │   └── feature_engineering.py
│   └── ml/
│       ├── training/              # NEW: Model training
│       ├── optimization/          # NEW: TensorRT optimization
│       └── inference/             # NEW: Inference utilities
├── aquila/                        # NEW: C++ inference engine
│   ├── CMakeLists.txt
│   ├── src/
│   │   ├── main.cpp
│   │   ├── model_runtime.cpp
│   │   ├── preprocessing.cpp
│   │   └── api_server.cpp
│   ├── include/
│   ├── tests/
│   └── docker/
├── api/                           # NEW: FastAPI backend
│   ├── main.py
│   ├── routers/
│   ├── services/
│   └── models/
├── dashboard/                     # NEW: React frontend
│   ├── src/
│   ├── public/
│   └── package.json
├── benchmarks/                    # NEW: Performance benchmarks
│   └── gpu_vs_cpu/
│       ├── benchmark_data_loading.py
│       └── results/
├── docs/
│   ├── AQUILA_ROADMAP.md   # NEW: Complete enhancement plan
│   ├── QUICK_START_PHASE1.md     # NEW: Quick start guide
│   └── GPU_PERFORMANCE.md         # NEW: Performance analysis
├── IMPLEMENTATION_TRACKER.md      # NEW: Task tracking
├── PROJECT_SUMMARY.md             # NEW: This overview
└── TODO.md                        # NEW: Action items
```

## Getting Started

1. **Read the docs:**

   - `PROJECT_SUMMARY.md` (you are here!)
   - `docs/AQUILA_ROADMAP.md` - Full plan
   - `docs/QUICK_START_PHASE1.md` - Start coding

2. **Set up environment:**

   ```bash
   # Choose your path:
   docker pull rapidsai/rapidsai:23.10-cuda11.8-runtime-ubuntu22.04-py3.10
   # OR
   # Use Paperspace, Colab, or AWS
   ```

3. **Run first benchmark:**

   ```bash
   cd benchmarks/gpu_vs_cpu
   python benchmark_data_loading.py
   ```

4. **Track progress:**
   - Update `IMPLEMENTATION_TRACKER.md` weekly
   - Check off items in `TODO.md`
   - Document wins in `docs/GPU_PERFORMANCE.md`

## Success Definition

**Project is successful when:**

- ✅ Can demonstrate 20x+ speedup with RAPIDS
- ✅ Inference latency <5ms with TensorRT
- ✅ Full-stack demo is deployable
- ✅ Documentation tells compelling story

**You're successful when:**

- ✅ Learned cutting-edge GPU computing
- ✅ Built production ML system end-to-end

---

**Last Updated:** October 30, 2025  
**Status:** Ready to begin Phase 1! 🚀
