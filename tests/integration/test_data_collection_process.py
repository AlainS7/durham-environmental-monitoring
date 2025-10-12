
import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock
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
def mock_db(mocker):
    # DB logic removed for BigQuery-only mode
    mock_db_instance = MagicMock()
    mock_engine = MagicMock()
    mock_connection = MagicMock()
    mock_connection.execute = MagicMock() # Explicitly mock the execute method
    mock_transaction = MagicMock()

    mock_db_instance.engine = mock_engine
    mock_engine.connect.return_value.__enter__.return_value = mock_connection
    mock_connection.begin.return_value.__enter__.return_value = mock_transaction
     # DB logic removed for BigQuery-only mode
    # mocker.patch('src.data_collection.daily_data_collector.HotDurhamDB', return_value=mock_db_instance)

    mocker.patch('pandas.read_sql', return_value=pd.DataFrame({
        'deployment_pk': [1, 2],
        'native_sensor_id': ['KNCGARNE13', 'd14rfblfk2973f196c5g'],
        'sensor_type': ['WU', 'TSI']
    }))
    mocker.patch('pandas.DataFrame.to_sql')

    return mock_db_instance, mock_connection

@pytest.mark.asyncio
async def test_run_collection_process_success(mock_clients, mock_db):
    """Test successful execution of the data collection process."""
    mock_wu_client, mock_tsi_client = mock_clients
    mock_db_instance, mock_connection = mock_db
    # Mock the new insertion method
    mock_db_instance.insert_sensor_readings = MagicMock()

    start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = start_date

    # Force sink to 'db' to avoid dependency on GCS bucket env vars in test
    await run_collection_process(start_date, end_date, is_dry_run=False, sink='db')

    # Verify clients were called with the correct signature
    mock_wu_client.fetch_data.assert_called_once_with(start_date, end_date)
    mock_tsi_client.fetch_data.assert_called_once_with(start_date, end_date)

    # Verify the new database insertion method was called
    # Should have been called at least once if data rows exist
    assert mock_db_instance.insert_sensor_readings.call_count >= 1
    
    # Optional: inspect the DataFrame passed to the method
    final_df = mock_db_instance.insert_sensor_readings.call_args[0][0]
    assert not final_df.empty
    assert 'deployment_fk' in final_df.columns
