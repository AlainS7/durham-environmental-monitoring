import datetime as dt

import scripts.check_residence_freshness_parity as mod


class _FakeRow(dict):
    pass


class _FakeQueryJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class _FakeClient:
    def __init__(self, values):
        self.values = values

    def query(self, q):
        if ".sensors." in q:
            return _FakeQueryJob([_FakeRow({"max_day": self.values["prod"]})])
        return _FakeQueryJob([_FakeRow({"max_day": self.values["shared"]})])


def test_read_max_day_returns_date():
    client = _FakeClient({"prod": dt.date(2026, 4, 1), "shared": dt.date(2026, 4, 1)})
    got = mod._read_max_day(client, "proj", "sensors", "residence_readings_daily")
    assert got == dt.date(2026, 4, 1)


def test_parity_lag_calculation():
    prod = dt.date(2026, 4, 2)
    shared = dt.date(2026, 4, 1)
    assert (prod - shared).days == 1

