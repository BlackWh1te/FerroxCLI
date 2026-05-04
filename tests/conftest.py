"""Pytest configuration and fixtures for FerroxCLI tests"""
import asyncio
import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ferrox.agent.orchestrator import FerroxAgent
from ferrox.config import get_default_config


@pytest.fixture
def sample_config():
    """Provide a test configuration"""
    return get_default_config()


@pytest.fixture
def sample_agent(sample_config):
    """Provide a test agent instance"""
    return FerroxAgent(sample_config)


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory"""
    return tmp_path


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_text_file(temp_dir):
    """Provide a sample text file for testing"""
    file_path = temp_dir / "test.txt"
    file_path.write_text("Hello, World!")
    return file_path


@pytest.fixture
def sample_python_file(temp_dir):
    """Provide a sample Python file for testing"""
    file_path = temp_dir / "test.py"
    file_path.write_text("""
def hello():
    return "Hello, World!"

if __name__ == "__main__":
    print(hello())
""")
    return file_path
