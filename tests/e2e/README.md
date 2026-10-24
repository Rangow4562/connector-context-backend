# E2E Tests

## Setup

```bash
pip install -r requirements.txt
```

## Run Tests

```bash
# All tests
pytest smoke/

# Specific file
pytest smoke/test_sources.py

# With options
pytest smoke/ -v              # verbose
pytest smoke/ -n auto         # parallel
pytest smoke/ -x              # stop on first failure
pytest smoke/ -m "not slow"   # skip slow tests
```

That's it.
