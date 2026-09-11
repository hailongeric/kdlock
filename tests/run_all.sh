#!/bin/bash
# Keep the familiar entry point, but require an explicit regression scope.
# Selection/listing is harmless; regression.py guards all guest execution.
set -euo pipefail
exec python3 "$(dirname "$0")/regression.py" "$@"
