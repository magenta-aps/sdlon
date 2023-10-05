#!/bin/bash
# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0

set -o nounset
set -o errexit
set -o pipefail

# Apply Alembic migrations
alembic upgrade head

# Run app
uvicorn --factory sdlon.main:create_app --host 0.0.0.0

# docker-compose.yaml used to invoke the app like this:
# uvicorn sdlon.main:app --host 0.0.0.0 --reload
# Seems to be for local development?
