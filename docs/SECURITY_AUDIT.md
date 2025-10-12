# Security Audit Configuration

This project uses `pip-audit` to scan for known vulnerabilities in Python dependencies. 

## Current Status

- **GHSA-4xh5-x5gv-qwph**: This is a known vulnerability in pip 25.2 related to tarfile extraction. The fix is planned for pip 25.3 but has not been released yet. This vulnerability requires a malicious sdist package to be exploited, so the risk is low for typical usage.

## Running Security Audit

To run the security audit locally:

```bash
uv run pip-audit --skip-editable --ignore-vuln GHSA-4xh5-x5gv-qwph
```

The flags used:
- `--skip-editable`: Skips the local package that isn't on PyPI
- `--ignore-vuln GHSA-4xh5-x5gv-qwph`: Temporarily ignores the pip vulnerability until 25.3 is released

## CI/CD Integration

The security audit is integrated into the CI pipeline in `.github/workflows/ci.yml` and will automatically run on pull requests and pushes to the main branch.