import scripts.check_row_thresholds as mod

class FakeResultRow(dict):
    pass

class FakeJob:
    def __init__(self, rows):
        self._rows = rows
    def result(self):
        return [FakeResultRow({'c': self._rows})]

class FakeClient:
    def __init__(self, counts):
        self.counts = counts
        self.project = 'proj'
    def query(self, q, job_config=None):
        # extract table name between backticks
        table = q.split('`')[1].split('.')[-1]
        return FakeJob(self.counts.get(table, 0))


def run_script(counts, date='2025-08-26', thresholds=None):
    thresholds = thresholds or {'wu_raw_materialized': 5}
    # monkeypatch load_thresholds to return provided thresholds
    orig_load = mod.load_thresholds
    mod.load_thresholds = lambda *a, **k: thresholds
    try:
        client = FakeClient(counts)
        failures = []
        results = {}
        for table, minimum in thresholds.items():
            try:
                cnt = mod.count_partition(client, 'proj', 'ds', table, date)  # type: ignore[arg-type]
                results[table] = {'count': cnt, 'min_required': minimum}
                if cnt < minimum:
                    failures.append(table)
            except Exception as e:
                results[table] = {'error': str(e)}
                failures.append(table)
        return failures, results
    finally:
        mod.load_thresholds = orig_load


def test_threshold_pass():
    failures, results = run_script({'wu_raw_materialized': 6})
    assert not failures
    assert results['wu_raw_materialized']['count'] == 6


def test_threshold_fail():
    failures, results = run_script({'wu_raw_materialized': 2})
    assert failures == ['wu_raw_materialized']
    assert results['wu_raw_materialized']['count'] == 2
