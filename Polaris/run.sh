#!/bin/sh
# Start the merged Polaris website on http://localhost:3100 (builds first if needed).
set -eu
cd "$(dirname "$0")/web"
[ -d node_modules ] || npm install
[ -f .next/BUILD_ID ] || npm run build
exec npm run start:prod
