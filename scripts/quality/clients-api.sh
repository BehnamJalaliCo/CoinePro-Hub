#!/usr/bin/env bash
# The owner's apps against the hub's OpenAPI: paths that exist and `limit` within each route's maximum.
set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/clients_api.py"
