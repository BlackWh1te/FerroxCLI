"""Tests for ferrox.tools module"""
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from ferrox.tools import execute_read_file, execute_run_command, execute_list_directory


class TestExecuteReadFile:
    """Test file reading functionality"""

    def test_read_existing_file(self):
        """Test reading an existing file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Test content")
            f.flush()
            temp_path = f.name

        try:
            result = execute_read_file(temp_path)
            assert result["success"] is True
            assert "Test content" in result["content"]
        finally:
            os.unlink(temp_path)

    def test_read_nonexistent_file(self):
        """Test reading a nonexistent file"""
        result = execute_read_file("/nonexistent/file.txt")
        assert result["success"] is False
        assert "error" in str(result).lower()

    def test_read_file_with_max_lines(self):
        """Test reading file with max_lines limit"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Line 1\nLine 2\nLine 3\nLine 4\nLine 5")
            f.flush()
            temp_path = f.name

        try:
            result = execute_read_file(temp_path, max_lines=2)
            assert result["success"] is True
            assert "Line 1" in result["content"]
            assert "Line 2" in result["content"]
        finally:
            os.unlink(temp_path)


class TestExecuteRunCommand:
    """Test command execution functionality"""

    def test_run_simple_command(self):
        """Test running a simple command"""
        result = execute_run_command("echo 'Hello World'")
        assert result["success"] is True
        assert "Hello World" in result["stdout"]

    def test_run_command_with_cwd(self):
        """Test running command in specific directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = execute_run_command("pwd" if os.name != 'nt' else "cmd /c echo test", cwd=temp_dir)
            assert result["success"] is True

    def test_run_invalid_command(self):
        """Test running an invalid command"""
        result = execute_run_command("nonexistent_command_12345")
        assert result["success"] is False

    @pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
    def test_run_command_with_timeout(self):
        """Test command with timeout"""
        result = execute_run_command("sleep 10")
        assert result["success"] is False


class TestExecuteListDirectory:
    """Test directory listing functionality"""

    def test_list_current_directory(self):
        """Test listing current directory"""
        result = execute_list_directory(".")
        assert "Contents of" in result
        assert isinstance(result, str)

    def test_list_specific_directory(self):
        """Test listing a specific directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "test1.txt").touch()
            Path(temp_dir, "test2.txt").touch()

            result = execute_list_directory(temp_dir)
            assert "test1.txt" in result
            assert "test2.txt" in result

    def test_list_nonexistent_directory(self):
        """Test listing a nonexistent directory"""
        result = execute_list_directory("/nonexistent/directory")
        assert "Error" in result


class TestToolErrorHandling:
    """Test error handling in tools"""

    def test_read_file_permission_error(self):
        """Test handling permission errors"""
        if os.name != 'nt':
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                temp_path = f.name

            try:
                os.chmod(temp_path, 0o000)
                result = execute_read_file(temp_path)
                assert result["success"] is False
            finally:
                os.chmod(temp_path, 0o644)
                os.unlink(temp_path)

    def test_command_execution_error(self):
        """Test handling command execution errors"""
        result = execute_run_command("exit 1" if os.name != 'nt' else "cmd /c exit 1")
        assert result["success"] is False


class TestToolIntegration:
    """Test integration between tools"""

    def test_read_then_list_directory(self):
        """Test reading a file then listing its directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir, "test.txt")
            test_file.write_text("Test content")

            read_result = execute_read_file(str(test_file))
            assert read_result["success"] is True

            list_result = execute_list_directory(temp_dir)
            assert "test.txt" in list_result

    def test_command_in_directory(self):
        """Test running command in directory we just listed"""
        with tempfile.TemporaryDirectory() as temp_dir:
            list_result = execute_list_directory(temp_dir)
            assert isinstance(list_result, str)

            cmd_result = execute_run_command(
                "pwd" if os.name != 'nt' else "cmd /c echo test",
                cwd=temp_dir
            )
            assert cmd_result["success"] is True
