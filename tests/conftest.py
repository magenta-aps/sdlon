from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_graphql_client():
    return MagicMock()
