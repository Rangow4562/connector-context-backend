"""Storage backend integration tests.

These tests run against real cloud infrastructure:
- AWS S3: connector-context-storage-backend-tests bucket
- GCP GCS: connector-context-storage-backend-tests bucket
- Azure Blob: backend-tests container in connector_contextcoredevstorage

Tests use unique prefixes for isolation and clean up after themselves.
"""
