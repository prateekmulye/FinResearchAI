"""API v2 routers (WP-5). Each module exposes a focused APIRouter that
``src.api.main.create_app`` mounts under the ``/api`` prefix:

  analyze.py  POST /api/analyze                       (SSE graph stream)
  library.py  GET  /api/library, GET /api/runs/{id}   (Research Library)
  market.py   GET  /api/market/...                    (Market Explorer reads)
  eval.py     GET  /api/eval/results                  (debate A/B results)
  quota.py    GET  /api/quota                         (demo-guard status)

Shared request dependencies live in deps.py; response DTOs in dto.py.
"""
