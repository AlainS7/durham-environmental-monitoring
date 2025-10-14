
import pytest
import pandas as pd
from unittest.mock import AsyncMock
from datetime import datetime, timedelta

from src.data_collection.daily_data_collector import run_collection_process

@pytest.fixture
def mock_clients(mocker):
    """Mocks WUClient and TSIClient fetch_data methods."""
    # Sample data for WUClient
    wu_data = {
        'stationID': ['KNCGARNE13'],
        'obsTimeUtc': ['2025-07-27T12:00:00Z'],
        'tempAvg': [25.0],
        'humidityAvg': [60.0]
    }
    tsi_data = {
        'cloud_device_id': ['d14rfblfk2973f196c5g'],
        'cloud_timestamp': ['2025-07-27T12:00:00Z'],
        'mcpm2x5': [15.5],
        'temperature': [26.0],
        'rh': [55.0]
    }
    wu_client = AsyncMock()
    tsi_client = AsyncMock()
    wu_client.fetch_data.return_value = pd.DataFrame(wu_data)
    tsi_client.fetch_data.return_value = pd.DataFrame(tsi_data)
    # Patch the class-level __aenter__ so any instance returns our mock
    mocker.patch('src.data_collection.clients.wu_client.WUClient.__aenter__', return_value=wu_client)
    mocker.patch('src.data_collection.clients.tsi_client.TSIClient.__aenter__', return_value=tsi_client)
    return wu_client, tsi_client

@pytest.fixture
    # DB logic removed for BigQuery-only mode

@pytest.mark.asyncio
async def test_run_collection_process_success(mock_clients):
    """Test successful execution of the data collection process."""
    mock_wu_client, mock_tsi_client = mock_clients
    start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = start_date

    # Run with BigQuery-only sink
    await run_collection_process(start_date, end_date, is_dry_run=False, sink='both')

    # Verify clients were called with the correct signature
    mock_wu_client.fetch_data.assert_called_once_with(start_date, end_date)
    mock_tsi_client.fetch_data.assert_called_once_with(start_date, end_date)
    # Optional: add BigQuery output checks here if needed
