import asyncio
import pandas as pd
from datetime import datetime

import src.data_collection.daily_data_collector as dc

class DummyWU:
    async def fetch_data(self, *a, **k):
        return pd.DataFrame({'stationID':['S1'], 'obsTimeUtc':[datetime(2025,8,26,12,0,0)], 'tempAvg':[23.4]})
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc, tb): return False
class DummyTSI:
    async def fetch_data(self, *a, **k):
        return pd.DataFrame({'device_id':['D1'], 'cloud_timestamp':[datetime(2025,8,26,12,5,0)], 'mcpm2x5':[11.1]})
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc, tb): return False

class DummyUploader:
    def __init__(self):
        self.uploads = []
    def upload_parquet(self, df, source, aggregated, interval, ts_column, **kw):
        self.uploads.append((source, len(df)))


class DummyDB:
    def __init__(self, *a, **k):
        class _Engine:
            def connect(self):
                class _Conn:
                    def __enter__(self): return self
                    def __exit__(self, *exc): return False
                    def execute(self, *a, **k): return None
                return _Conn()
        self.engine = _Engine()
    def insert_sensor_readings(self, df):
        return True

# Patch clients and uploader builder

def test_run_collection_process_gcs(monkeypatch):
    monkeypatch.setattr(dc, 'WUClient', lambda **cfg: DummyWU())
    monkeypatch.setattr(dc, 'TSIClient', lambda **cfg: DummyTSI())
    monkeypatch.setattr(dc, '_build_uploader', lambda bucket, prefix: DummyUploader())
    # monkeypatch.setattr(dc, 'HotDurhamDB', DummyDB)
     # DB logic removed for BigQuery-only mode
    # ensure bucket config so GCS path executes; force fake upload to avoid pyarrow if missing
    monkeypatch.setenv('GCS_FAKE_UPLOAD', '1')
    # run with gcs sink only to avoid DB connection attempt
    asyncio.run(dc.run_collection_process(datetime(2025,8,26), datetime(2025,8,26), sink='gcs', source='all'))


def test_run_collection_process_dry(monkeypatch, capsys):
    monkeypatch.setattr(dc, 'WUClient', lambda **cfg: DummyWU())
    monkeypatch.setattr(dc, 'TSIClient', lambda **cfg: DummyTSI())
    asyncio.run(dc.run_collection_process(datetime(2025,8,26), datetime(2025,8,26), sink='gcs', source='all', is_dry_run=True))
    captured = capsys.readouterr()
    assert 'WU sample' in captured.out
