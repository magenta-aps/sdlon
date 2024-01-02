#!/bin/bash
# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0

set -o nounset
set -o errexit
set -o pipefail

# Apply Alembic migrations
alembic upgrade head

# Run app
if [ "$ENVIRONMENT" = "development" ]; then
    echo "Running in development mode (hot-reload)"
    uvicorn --factory sdlon.main:create_app --host 0.0.0.0 --reload
else
    echo "Running in production mode"
    uvicorn --factory sdlon.main:create_app --host 0.0.0.0
fi
