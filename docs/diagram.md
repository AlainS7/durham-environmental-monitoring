# Hot Durham Project - System Architecture

```mermaid
graph TD
%% --- Chart Title ---
accTitle: Hot Durham Project - System Architecture

%% =============================================
%%  1. DEFINE ALL NODES FIRST
%% =============================================
TSI_API("fa:fa-cloud TSI API")
WU_API("fa:fa-cloud-sun Weather Underground API")
DC("fa:fa-python daily_data_collector.py")
CONFIG("fa:fa-file-code Configuration Files")
DB_TABLES("fa:fa-table Tables<br>[tsi_data, wu_data, metadata, log]")
DB_VIEWS("fa:fa-table-list Views<br>[readings, metadata_view, etc.]")
LS("fa:fa-chart-simple Looker Studio")
BACKEND("fa:fa-server Backend API<br>(src/api/main.py)")
FRONTEND("fa:fa-window-maximize Web Dashboard (UI)")
GHA("fa:fa-github GitHub Actions (CI/CD)")
CS("fa:fa-clock Cloud Scheduler")
DB_VERIFY("fa:fa-check-double scripts/verify_db_data.py")


%% =============================================
%%  2. GROUP NODES INTO SUBGRAPHS (FIXED TITLES)
%% =============================================
subgraph "External Data Sources"
    direction LR
    TSI_API & WU_API
end

subgraph "Data Ingestion & Processing"
    DC & CONFIG
end

subgraph "Data Storage"
    direction TB
    subgraph "PostgreSQL Database"
        DB_TABLES -- Feeds --> DB_VIEWS
    end
end

subgraph "Data Consumption & Presentation"
    direction LR
    LS & BACKEND & FRONTEND
end

subgraph "Automation & Monitoring"
    direction LR
    GHA & CS & DB_VERIFY
end

%% =============================================
%%  3. DEFINE CONNECTIONS BETWEEN NODES
%% =============================================
%% Ingestion Flow
TSI_API --> DC
WU_API --> DC
CONFIG --> DC
DC -- Inserts & Updates --> DB_TABLES

%% Consumption Flow
DB_VIEWS -- Queried by --> LS
DB_TABLES -- Queried by --> LS
DB_TABLES -- Queried by --> BACKEND
BACKEND -- Serves Data --> FRONTEND

%% Automation Flow
CS -- Triggers Daily --> DC
GHA -- Deploys & Builds --> DC
GHA -- Deploys & Builds --> BACKEND
GHA -- Deploys & Builds --> FRONTEND
DB_VERIFY -- Verifies Data Integrity --> DB_TABLES


%% =============================================
%%  4. APPLY STYLING
%% =============================================
classDef sources fill:#e0f7fa,stroke:#00796b,stroke-width:2px
class TSI_API,WU_API sources

classDef processing fill:#fff9c4,stroke:#fbc02d,stroke-width:2px
class DC,CONFIG,DB_VERIFY processing

classDef storage fill:#ede7f6,stroke:#5e35b1,stroke-width:2px
class DB_TABLES,DB_VIEWS storage

classDef consumption fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
class LS,BACKEND,FRONTEND consumption

classDef automation fill:#eceff1,stroke:#546e7a,stroke-width:2px
class GHA,CS automation
```
