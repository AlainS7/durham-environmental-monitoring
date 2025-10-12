# Requirements Files

This project contains generated requirements files for reference and specific use cases:

- `requirements.txt`: Production dependencies only
- `requirements-dev.txt`: Production + development dependencies

## ⚠️ Important Note

**Do not use `pip sync` or `pip install -r` with both files simultaneously** as they may contain conflicting dependency versions.

## Recommended Usage

### For Development (Local)
```bash
uv pip install -e ".[dev]"
```

### For Production
```bash
uv pip install -e .
```

### For CI/CD
The CI workflow uses `uv pip install -e ".[dev]"` which automatically resolves dependencies from `pyproject.toml`.

### Generating Requirements Files
If you need to regenerate the requirements files:

```bash
# Production dependencies
uv pip compile pyproject.toml --output-file requirements.txt

# Development dependencies  
uv pip compile pyproject.toml --extra dev --output-file requirements-dev.txt
```

The generated files are useful for:
- Auditing dependencies
- Creating Docker images with specific versions
- Analyzing dependency trees
- Ensuring reproducible builds

But should not be used for local development or CI setup.