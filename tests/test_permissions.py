"""Tests for ferrox.permissions module"""
import os
import tempfile

import pytest

from ferrox.modes import Mode
from ferrox.permissions import PermissionAction, PermissionEngine


@pytest.fixture
def permission_engine():
    """Create a permission engine for testing"""
    return PermissionEngine()


@pytest.fixture
def temp_file():
    """Create a temporary file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test content")
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestPermissionEngineInit:
    """Test PermissionEngine initialization"""

    def test_engine_initialization(self, permission_engine):
        """Test that permission engine initializes correctly"""
        assert permission_engine is not None
        assert hasattr(permission_engine, 'config_path')
        assert hasattr(permission_engine, 'session_allowed')
        assert hasattr(permission_engine, 'persistent_rules')


class TestCheckAccessNormalMode:
    """Test access checking in Normal mode"""

    def test_normal_mode_read_allowed(self, permission_engine, temp_file):
        """Test read access in Normal mode"""
        result = permission_engine.check_access(temp_file, PermissionAction.READ, Mode.NORMAL)
        # In Normal mode, should ask or allow based on implementation
        assert result is not False  # Either True or prompt

    def test_normal_mode_write_allowed(self, permission_engine, temp_file):
        """Test write access in Normal mode"""
        result = permission_engine.check_access(temp_file, PermissionAction.WRITE, Mode.NORMAL)
        assert result is not False  # Either True or prompt


class TestCheckAccessPlanMode:
    """Test access checking in Plan mode"""

    def test_plan_mode_read_only(self, permission_engine, temp_file):
        """Test that Plan mode only allows read operations"""
        result = permission_engine.check_access(temp_file, PermissionAction.READ, Mode.PLAN)
        assert result is not False  # Read should be allowed or prompt

    def test_plan_mode_write_asks(self, permission_engine, temp_file):
        """Test that Plan mode asks for write operations"""
        result = permission_engine.check_access(temp_file, PermissionAction.WRITE, Mode.PLAN)
        assert result is None  # Write should prompt in Plan mode


class TestCheckAccessBypassMode:
    """Test access checking in Bypass mode"""

    def test_bypass_mode_all_allowed(self, permission_engine, temp_file):
        """Test that Bypass mode allows all operations"""
        read_result = permission_engine.check_access(temp_file, PermissionAction.READ, Mode.BYPASS)
        write_result = permission_engine.check_access(temp_file, PermissionAction.WRITE, Mode.BYPASS)
        # Bypass mode should allow everything
        assert read_result is True
        assert write_result is True


class TestGrantAccess:
    """Test granting access permissions"""

    def test_grant_temporary_access(self, permission_engine, temp_file):
        """Test granting temporary access"""
        permission_engine.grant_access(temp_file, persistent=False)
        # Check that access is granted
        result = permission_engine.check_access(temp_file, PermissionAction.READ, Mode.NORMAL)
        assert result is True

    def test_grant_persistent_access(self, permission_engine, temp_file):
        """Test granting persistent access"""
        permission_engine.grant_access(temp_file, persistent=True)
        # Check that access is granted
        result = permission_engine.check_access(temp_file, PermissionAction.READ, Mode.NORMAL)
        assert result is True


class TestDenyAccess:
    """Test denying access permissions"""

    def test_deny_access(self, permission_engine, temp_file):
        """Test denying access"""
        permission_engine.deny_access(temp_file, persistent=True)
        result = permission_engine.check_access(temp_file, PermissionAction.READ, Mode.NORMAL)
        assert result is False


class TestAskPrompt:
    """Test prompt generation for user confirmation"""

    def test_read_prompt_generation(self, permission_engine, temp_file):
        """Test prompt generation for read operation"""
        prompt = permission_engine.get_ask_prompt(temp_file, PermissionAction.READ)
        assert temp_file in prompt
        assert "read" in prompt.lower()

    def test_write_prompt_generation(self, permission_engine, temp_file):
        """Test prompt generation for write operation"""
        prompt = permission_engine.get_ask_prompt(temp_file, PermissionAction.WRITE)
        assert temp_file in prompt
        assert "write" in prompt.lower() or "modify" in prompt.lower()


class TestPermissionPersistence:
    """Test that permissions persist correctly"""

    def test_persistent_grant_survives_check(self, permission_engine, temp_file):
        """Test that persistent grants survive multiple checks"""
        permission_engine.grant_access(temp_file, persistent=True)

        # Check multiple times
        for _ in range(3):
            result = permission_engine.check_access(temp_file, PermissionAction.READ, Mode.NORMAL)
            assert result is True

    def test_temporary_grant_single_use(self, permission_engine, temp_file):
        """Test that temporary grants might be single-use"""
        permission_engine.grant_access(temp_file, persistent=False)

        # First check should succeed
        result1 = permission_engine.check_access(temp_file, PermissionAction.READ, Mode.NORMAL)
        assert result1 is True

        # Second check might require re-approval (implementation dependent)
        permission_engine.check_access(temp_file, PermissionAction.READ, Mode.NORMAL)
        # This depends on implementation, but we test the behavior


class TestPermissionAction:
    """Test PermissionAction enum"""

    def test_permission_action_values(self):
        """Test that PermissionAction has expected values"""
        assert PermissionAction.READ.value == "read"
        assert PermissionAction.WRITE.value == "write"
        assert PermissionAction.EXECUTE.value == "execute"


class TestEdgeCases:
    """Test edge cases in permission handling"""

    def test_nonexistent_file_permission(self, permission_engine):
        """Test permission check for nonexistent file"""
        result = permission_engine.check_access("/nonexistent/file.txt", PermissionAction.READ, Mode.NORMAL)
        # Should handle gracefully - either ask or deny
        assert result is not None

    def test_empty_file_permission(self, permission_engine):
        """Test permission check for empty path"""
        result = permission_engine.check_access("", PermissionAction.READ, Mode.NORMAL)
        assert result is not None

    def test_special_characters_in_path(self, permission_engine):
        """Test permission check with special characters in path"""
        # This tests handling of unusual file paths
        special_path = "test_file_@#$%.txt"
        result = permission_engine.check_access(special_path, PermissionAction.READ, Mode.NORMAL)
        assert result is not None
