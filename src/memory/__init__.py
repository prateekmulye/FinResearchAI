# src/memory package — supersedes the legacy src/memory.py module.
# WP-I will delete the legacy module.

# Backward-compat alias: old reporter.py imports VectorMemory (renamed to VectorStore in WP-D).
from src.memory.store import VectorStore as VectorMemory  # noqa: F401
