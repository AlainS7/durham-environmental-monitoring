import pytest
import pandas as pd

# Use the main data collection process for integration testing
from src.data_collection.daily_data_collector import run_collection_process

@pytest.fixture
def sample_wu_df():
    """Creates a sample Weather Underground DataFrame for testing."""
    # Ensure 'native_sensor_id' is a column and not an index
    df = pd.DataFrame({
        'native_sensor_id': ['KNCGARNE13', 'KNCGARNE13', 'd14rfblfk2973f196c5g'],
        'timestamp': ['2025-07-27T12:00:00Z', '2025-07-27T13:00:00Z', '2025-07-27T14:00:00Z'],
        'temperature': [25, 26, 27],
        'humidity': [60, 61, 62]
    })
    df = df.reset_index(drop=True)
    return df

@pytest.fixture
def sample_tsi_df():
    """Creates a sample TSI DataFrame for testing."""
    data = {
        'native_sensor_id': ['TSI_PROD_X', 'TSI_PROD_Y', 'TSI_TEST_A'],
        'PM2.5': [10.1, 12.3, 15.5]
    }
    return pd.DataFrame(data)


# Integration test for the main data collection process


@pytest.mark.asyncio
async def test_main_script_flow(mocker, sample_wu_df, sample_tsi_df):
    """
    Integration test for the main data collection process.
    Mocks WUClient, TSIClient, and DB interactions to verify end-to-end logic.
    """
    # Mock WUClient and TSIClient fetch_data methods and patch class-level __aenter__
    mock_wu_client = mocker.AsyncMock()
    mock_tsi_client = mocker.AsyncMock()
    mock_wu_client.fetch_data.return_value = sample_wu_df
    mock_tsi_client.fetch_data.return_value = sample_tsi_df
    mocker.patch('src.data_collection.clients.wu_client.WUClient.__aenter__', return_value=mock_wu_client)
    mocker.patch('src.data_collection.clients.tsi_client.TSIClient.__aenter__', return_value=mock_tsi_client)

    # Patch pandas.read_sql to return a valid DataFrame for deployment map (BigQuery-only)
    mocker.patch('pandas.read_sql', return_value=pd.DataFrame({
        'native_sensor_id': ['KNCGARNE13', 'KNCGARNE13', 'd14rfblfk2973f196c5g'],
        'sensor_type': ['WU', 'WU', 'TSI']
    }))

    # Run the main collection process
    start_date = '2025-07-27'
    end_date = '2025-07-27'
    await run_collection_process(start_date, end_date, is_dry_run=False, sink='both')

    # Assert that the clients were called
    mock_wu_client.fetch_data.assert_called_once_with(start_date, end_date)
    mock_tsi_client.fetch_data.assert_called_once_with(start_date, end_date)
