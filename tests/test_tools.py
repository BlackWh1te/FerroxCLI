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
            result = execute_read_file({"file_path": temp_path})
            assert "Test content" in result
            assert result["success"] is True
        finally:
            os.unlink(temp_path)
    
    def test_read_nonexistent_file(self):
        """Test reading a nonexistent file"""
        result = execute_read_file({"file_path": "/nonexistent/file.txt"})
        assert result["success"] is False
        assert "error" in result.lower()
    
    def test_read_file_with_lines(self):
        """Test reading file with specific line range"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Line 1\nLine 2\nLine 3\nLine 4\nLine 5")
            f.flush()
            temp_path = f.name
        
        try:
            result = execute_read_file({"file_path": temp_path, "offset": 2, "limit": 2})
            assert result["success"] is True
            assert "Line 3" in result
            assert "Line 4" in result
        finally:
            os.unlink(temp_path)


class TestExecuteRunCommand:
    """Test command execution functionality"""
    
    def test_run_simple_command(self):
        """Test running a simple command"""
        result = execute_run_command({"command": "echo 'Hello World'"})
        assert result["success"] is True
        assert "Hello World" in result
    
    def test_run_command_with_cwd(self):
        """Test running command in specific directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = execute_run_command({
                "command": "echo 'test'",
                "cwd": temp_dir
            })
            assert result["success"] is True
    
    def test_run_invalid_command(self):
        """Test running an invalid command"""
        result = execute_run_command({"command": "nonexistent_command_12345"})
        assert result["success"] is False
    
    @pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
    def test_run_command_with_timeout(self):
        """Test command with timeout"""
        import time
        result = execute_run_command({
            "command": "sleep 10",
            "timeout": 1
        })
        assert result["success"] is False
        assert "timeout" in result.lower()


class TestExecuteListDirectory:
    """Test directory listing functionality"""
    
    def test_list_current_directory(self):
        """Test listing current directory"""
        result = execute_list_directory({"path": "."})
        assert result["success"] is True
        assert "items" in result
    
    def test_list_specific_directory(self):
        """Test listing a specific directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some test files
            Path(temp_dir, "test1.txt").touch()
            Path(temp_dir, "test2.txt").touch()
            
            result = execute_list_directory({"path": temp_dir})
            assert result["success"] is True
            assert len(result["items"]) >= 2
    
    def test_list_nonexistent_directory(self):
        """Test listing a nonexistent directory"""
        result = execute_list_directory({"path": "/nonexistent/directory"})
        assert result["success"] is False
    
    def test_list_directory_with_pattern(self):
        """Test listing directory with file pattern"""
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "test.py").touch()
            Path(temp_dir, "test.txt").touch()
            Path(temp_dir, "other.md").touch()
            
            result = execute_list_directory({
                "path": temp_dir,
                "pattern": "*.py"
            })
            assert result["success"] is True
            assert any("test.py" in item.get("name", "") for item in result["items"])


class TestToolErrorHandling:
    """Test error handling in tools"""
    
    def test_read_file_permission_error(self):
        """Test handling permission errors"""
        # Create a file with no read permissions (Unix only)
        if os.name != 'nt':
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                temp_path = f.name
            
            try:
                os.chmod(temp_path, 0o000)
                result = execute_read_file({"file_path": temp_path})
                assert result["success"] is False
            finally:
                os.chmod(temp_path, 0o644)
                os.unlink(temp_path)
    
    def test_command_execution_error(self):
        """Test handling command execution errors"""
        result = execute_run_command({"command": "exit 1"})
        # Command executes but returns non-zero exit code
        assert "exit code" in result.lower()


class TestToolIntegration:
    """Test integration between tools"""
    
    def test_read_then_list_directory(self):
        """Test reading a file then listing its directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir, "test.txt")
            test_file.write_text("Test content")
            
            # Read the file
            read_result = execute_read_file({"file_path": str(test_file)})
            assert read_result["success"] is True
            
            # List the directory
            list_result = execute_list_directory({"path": temp_dir})
            assert list_result["success"] is True
            assert any("test.txt" in item.get("name", "") for item in list_result["items"])
    
    def test_command_in_directory(self):
        """Test running command in directory we just listed"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # List directory first
            list_result = execute_list_directory({"path": temp_dir})
            assert list_result["success"] is True
            
            # Run command in same directory
            cmd_result = execute_run_command({
                "command": "pwd" if os.name != 'nt' else "cd",
                "cwd": temp_dir
            })
            assert cmd_result["success"] is True