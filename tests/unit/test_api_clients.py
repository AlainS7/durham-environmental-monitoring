
import pytest
from unittest.mock import MagicMock, patch

from src.data_collection.clients.wu_client import WUClient
from src.data_collection.clients.tsi_client import TSIClient

@pytest.fixture
def mock_app_config():
    """Fixture to mock the app_config object globally."""
    with patch('src.config.app_config.app_config', MagicMock()) as mock_config:
        mock_config.wu_api_config = {'api_key': 'test_key', 'base_url': 'https://fake-wu.com'}
        mock_config.tsi_api_config = {
            'client_id': 'test_id',
            'client_secret': 'test_secret',
            'auth_url': 'https://fake-tsi.com/auth',
            'base_url': 'https://fake-tsi.com/api'
        }
        yield mock_config

@pytest.mark.asyncio
async def test_wu_client_fetch_data_success(mocker):
    """Test successful data fetching for WUClient."""
    mock_response = {
        'observations': [
            {'stationID': 'KNCGARNE13', 'obsTimeUtc': '2025-07-27T12:00:00Z', 'tempAvg': 25.0, 'humidityAvg': 60.0}
        ]
    }
    
    mocker.patch('src.data_collection.clients.base_client.BaseClient._request', return_value=mock_response)
    mocker.patch('src.data_collection.clients.wu_client.get_wu_stations', return_value=[{'stationId': 'KNCGARNE13'}])

    client = WUClient(api_key='test_key', base_url='https://fake-wu.com')
    df = await client.fetch_data('2025-07-27', '2025-07-27')

    assert not df.empty
    assert df.iloc[0]['stationID'] == 'KNCGARNE13'
    assert df.iloc[0]['tempAvg'] == 25.0

@pytest.mark.asyncio
async def test_tsi_client_fetch_data_success(mocker):
    """Test successful data fetching for TSIClient."""
    # Mock telemetry response with the correct nested structure that TSI API returns
    telemetry_response = [
        {
            'cloud_timestamp': '2025-07-27T12:00:00Z',
            'cloud_device_id': 'd14rfblfk2973f196c5g',
            'cloud_account_id': 'test_account',
            'model': 'Model 8543',
            'metadata': {
                'location': {
                    'latitude': 35.9940,
                    'longitude': -78.8986
                },
                'is_indoor': False,
                'is_public': True
            },
            'sensors': [
                {
                    'serial': 'SN12345',
                    'measurements': [
                        {'name': 'PM 2.5', 'data': {'value': 15.5}},
                        {'name': 'Temperature', 'data': {'value': 26.0}},
                        {'name': 'Relative Humidity', 'data': {'value': 55.0}}
                    ]
                }
            ]
        }
    ]
    # Ensure the returned device list aligns with expectation in assertions
    mocker.patch('src.data_collection.clients.tsi_client.get_tsi_devices', return_value=['d14rfblfk2973f196c5g'])
    client = TSIClient(client_id='test_id', client_secret='test_secret', auth_url='https://fake-tsi.com/auth', base_url='https://fake-tsi.com/api')
    mocker.patch.object(client, '_authenticate', side_effect=lambda: setattr(client, 'headers', {"Authorization": "Bearer fake_token", "Accept": "application/json"}) or True)
    mocker.patch('src.data_collection.clients.base_client.BaseClient._request', return_value=telemetry_response)
    df = await client.fetch_data('2025-07-27', '2025-07-27')

    assert not df.empty, "TSI DataFrame should not be empty"
    assert 'timestamp' in df.columns, "Timestamp column should be present"
    assert (df['device_id'] == 'd14rfblfk2973f196c5g').all(), "All rows should have the test device id"
    assert df.iloc[0]['pm2_5'] == 15.5, "PM2.5 value should match test data"
    assert df.iloc[0]['temperature'] == 26.0, "Temperature value should match test data"
    assert df.iloc[0]['rh'] == 55.0, "Relative humidity value should match test data"

