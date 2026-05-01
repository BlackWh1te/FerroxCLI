"""Tools module for Ferrox - File system and shell tools"""

import os
import json
from typing import Any


def get_available_tools():
    """
    Returns the schema for tools the AI can use.
    Matches OpenAI function calling standard.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List all files and directories in a specific path. Use this when the user asks to 'check', 'look at', 'ls', or 'review' their project or directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The relative or absolute path to list. Default to '.' for current directory."
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the content of a text file. Only works with text files (code, JSON, Markdown, etc). Does NOT support images, binary files, or PDFs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to read."
                        },
                        "max_lines": {
                            "type": "number",
                            "description": "Maximum number of lines to read (optional, default 500)."
                        }
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a file with new content. Use this when the user asks to 'create', 'write', or 'save' a file. User will be asked to review changes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to write."
                        },
                        "content": {
                            "type": "string",
                            "description": "The content to write to the file."
                        }
                    },
                    "required": ["file_path", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file_direct",
                "description": "Write a file without asking for review. Use only for non-critical files like logs or temp files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to write."
                        },
                        "content": {
                            "type": "string",
                            "description": "The content to write to the file."
                        }
                    },
                    "required": ["file_path", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Run a shell command and return its output. Use this when the user asks to 'run', 'execute', or 'build' something.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute."
                        },
                        "cwd": {
                            "type": "string",
                            "description": "Working directory for the command (optional)."
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    ]


def execute_list_directory(path: str = ".") -> str:
    """Execute list_directory tool"""
    try:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return f"Error: Path does not exist: {abs_path}"
        if not os.path.isdir(abs_path):
            return f"Error: Not a directory: {abs_path}"

        items = os.listdir(abs_path)
        result = []
        for item in sorted(items):
            full_path = os.path.join(abs_path, item)
            if os.path.isdir(full_path):
                result.append(f"📁 {item}/")
            else:
                size = os.path.getsize(full_path)
                size_str = _format_size(size)
                result.append(f"📄 {item} ({size_str})")

        return f"Contents of {abs_path}:\n" + "\n".join(result)
    except Exception as e:
        return f"Error listing directory: {str(e)}"


def execute_read_file(file_path: str, max_lines: int = None) -> dict:
    """Execute read_file tool"""
    try:
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            return {"error": f"File does not exist: {file_path}", "success": False}

        with open(abs_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        total_lines = len(lines)
        read_lines = max_lines if max_lines and max_lines < total_lines else total_lines
        content = ''.join(lines[:read_lines])
        
        return {
            "file_path": file_path,
            "lines_read": (1, read_lines),
            "total_lines": total_lines,
            "content": content,
            "success": True
        }
    except Exception as e:
        return {"error": str(e), "success": False}


def execute_write_file(file_path: str, content: str) -> str:
    """Execute write_file tool"""
    try:
        abs_path = os.path.abspath(file_path)

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return f"Successfully wrote to {abs_path} ({len(content)} characters)"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def execute_run_command(command: str, cwd: str = None) -> dict:
    """Execute run_command tool"""
    import subprocess

    try:
        if cwd is None:
            cwd = os.getcwd()

        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )

        return {
            "command": command,
            "working_dir": cwd,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "success": result.returncode == 0
        }
    except Exception as e:
        return {"error": str(e), "exit_code": -1, "success": False}


def _format_size(size: int) -> str:
    """Format file size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size}{unit}"
        size /= 1024
    return f"{size}TB"


def execute_write_file_direct(file_path: str, content: str) -> str:
    """Execute write_file_direct - writes without review"""
    return execute_write_file(file_path, content)


TOOL_MAP = {
    "list_directory": execute_list_directory,
    "read_file": execute_read_file,
    "write_file": execute_write_file,
    "write_file_direct": execute_write_file_direct,
    "run_command": execute_run_command
}


def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool by name with arguments"""
    if tool_name not in TOOL_MAP:
        return f"Error: Tool '{tool_name}' not found"

    try:
        func = TOOL_MAP[tool_name]
        return func(**arguments)
    except Exception as e:
        return f"Error executing tool: {str(e)}"


def execute_write_file_with_review(file_path: str, content: str) -> tuple:
    """
    Execute write_file tool with diff review.
    Returns: (result_message: str, approved: bool)
    """
    from .diff import show_diff_and_prompt, apply_file_edit

    try:
        abs_path = os.path.abspath(file_path)

        original_content = ""
        if os.path.exists(abs_path):
            with open(abs_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

        accepted, edit_action = show_diff_and_prompt(original_content, content, file_path)

        if accepted:
            result = apply_file_edit(file_path, content)
            return (result, True)
        elif edit_action == "edit":
            return ("User chose to edit manually. Use /cfg to edit config.", False)
        else:
            return (f"User rejected changes to {file_path}", False)

    except Exception as e:
        return (f"Error during file review: {str(e)}", False)