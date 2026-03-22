import os
import sys

# Add castone/backend to Python path for absolute imports like `app.services...`
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../castone/backend"))
sys.path.insert(0, backend_path)

import pytest
import asyncio
from typing import Generator

# Enable pytest-asyncio auto mode
def pytest_configure(config):
    config.option.asyncio_mode = "auto"
