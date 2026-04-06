import pandas as pd
import pytest

from src.data_collection.clients.wu_client import EndpointStrategy, WUClient


@pytest.mark.asyncio
async def test_hybrid_builds_hourly_and_multiday_requests(mocker):
    mocker.patch(
        'src.data_collection.clients.wu_client.get_wu_stations',
        return_value=[{'stationId': 'KNCGARNE13'}],
    )
    client = WUClient(
        api_key='test_key',
        base_url='https://fake-wu.com',
        endpoint_strategy='hybrid',
    )

    requests = client._build_requests('2026-04-01', '2026-04-01')

    assert len(requests) == 2
    assert requests[0][3] == EndpointStrategy.HOURLY
    assert requests[1][3] == EndpointStrategy.MULTIDAY


@pytest.mark.asyncio
async def test_hybrid_merges_duplicate_timestamps_across_endpoints(mocker):
    mocker.patch(
        'src.data_collection.clients.wu_client.get_wu_stations',
        return_value=[{'stationId': 'KNCGARNE13'}],
    )
    client = WUClient(
        api_key='test_key',
        base_url='https://fake-wu.com',
        endpoint_strategy='hybrid',
    )

    hourly_df = pd.DataFrame(
        [
            {
                'stationID': 'KNCGARNE13',
                'obsTimeUtc': '2026-04-01T04:00:00Z',
                'tempAvg': 20.5,
                'humidityAvg': None,
            }
        ]
    )
    multiday_df = pd.DataFrame(
        [
            {
                'stationID': 'KNCGARNE13',
                'obsTimeUtc': '2026-04-01T04:00:00Z',
                'tempAvg': None,
                'humidityAvg': 65.0,
            },
            {
                'stationID': 'KNCGARNE13',
                'obsTimeUtc': '2026-04-01T04:15:00Z',
                'tempAvg': None,
                'humidityAvg': 66.0,
            },
        ]
    )

    mocker.patch.object(client, '_execute_fetches', return_value=[hourly_df, multiday_df])

    df = await client.fetch_data('2026-04-01', '2026-04-01')

    assert len(df) == 2
    merged_row = df[df['obsTimeUtc'] == pd.Timestamp('2026-04-01T04:00:00Z')].iloc[0]
    assert merged_row['tempAvg'] == 20.5
    assert merged_row['humidityAvg'] == 65.0


@pytest.mark.asyncio
async def test_multiday_uses_history_all_with_date_param(mocker):
    mocker.patch(
        'src.data_collection.clients.wu_client.get_wu_stations',
        return_value=[{'stationId': 'KNCGARNE13'}],
    )
    client = WUClient(
        api_key='test_key',
        base_url='https://fake-wu.com',
        endpoint_strategy='multiday',
    )

    calls = []

    async def _fake_request(method, endpoint, params=None):
        call = {
            'method': method,
            'endpoint': endpoint,
            'params': params or {},
        }
        calls.append(call)
        return {
            'observations': [
                {
                    'stationID': 'KNCGARNE13',
                    'obsTimeUtc': (
                        '2026-04-01T00:05:00Z'
                        if (params or {}).get('date') == '20260331'
                        else '2026-04-01T04:00:00Z'
                    ),
                }
            ]
        }

    mocker.patch.object(client, '_request', side_effect=_fake_request)

    df = await client._fetch_one(
        'KNCGARNE13',
        '2026-04-01',
        strategy=EndpointStrategy.MULTIDAY,
    )

    assert [c['method'] for c in calls] == ['GET', 'GET']
    assert all(c['endpoint'] == 'history/all' for c in calls)
    assert [c['params']['date'] for c in calls] == ['20260331', '20260401']
    assert not df.empty
    assert pd.Timestamp('2026-04-01T00:05:00Z') in set(df['obsTimeUtc'])
