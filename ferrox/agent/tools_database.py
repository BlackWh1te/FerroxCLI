"""Database interaction tools for Ferrox agent.

Provides database operations with permission checks and safety features.
Supports SQLite, PostgreSQL, and MySQL with read-only defaults.
"""

import os
from typing import Optional, Dict, List, Any
from pydantic_ai import RunContext

from ..permissions import PermissionEngine, PermissionAction
from ..modes import Mode
from ..exceptions import PermissionDeniedError, ToolExecutionError

# Import tracer
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

# Import _current_agent
try:
    from ferrox.agent.orchestrator import _current_agent
except ImportError:
    _current_agent = None

# Import output formatters
try:
    from ..ui.output import format_tool_call
except ImportError:
    format_tool_call = None

# Shared permission engine
permissions = PermissionEngine()


async def db_query_tool(ctx: RunContext, db_type: str, connection_string: str, query: str, read_only: bool = True) -> str:
    """Execute a SQL query on a database. Read-only by default for safety.
    
    Args:
        db_type: Database type (sqlite, postgresql, mysql)
        connection_string: Database connection string or file path for SQLite
        query: SQL query to execute
        read_only: If True, only allows SELECT queries (default: True)
    """
    with tracer.start_as_current_span("db_query_tool") as span:
        span.set_attribute("db_type", db_type)
        span.set_attribute("read_only", read_only)
        span.set_attribute("query", query[:100])  # Truncate for safety
        
        try:
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )
            
            # Check if query is write operation when read_only is True
            query_upper = query.strip().upper()
            if read_only and any(word in query_upper for word in ["INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"]):
                error_msg = "Write operation not allowed in read-only mode. Set read_only=False and ensure you have permission."
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("db_query", {"db_type": db_type})
                    _current_agent._log_tool_result("db_query", error_msg, False)
                return error_msg
            
            # Write operations require permission
            if not read_only and not permissions.check_access(connection_string, PermissionAction.WRITE, mode):
                error_msg = f"Permission denied: database write operations require write access to {connection_string}"
                span.set_attribute("access", "denied")
                if _current_agent:
                    _current_agent._log_tool_call("db_query", {"db_type": db_type})
                    _current_agent._log_tool_result("db_query", error_msg, False)
                return error_msg
            
            if format_tool_call:
                format_tool_call("db_query", {"db_type": db_type, "read_only": read_only})
            
            # Execute query based on database type
            if db_type == "sqlite":
                result = await _execute_sqlite(connection_string, query)
            elif db_type == "postgresql":
                result = await _execute_postgresql(connection_string, query)
            elif db_type == "mysql":
                result = await _execute_mysql(connection_string, query)
            else:
                error_msg = f"Unsupported database type: {db_type}. Supported: sqlite, postgresql, mysql"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("db_query", {"db_type": db_type})
                    _current_agent._log_tool_result("db_query", error_msg, False)
                return error_msg
            
            if result.get("error"):
                error_msg = f"Database query failed: {result['error']}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("db_query", {"db_type": db_type})
                    _current_agent._log_tool_result("db_query", error_msg, False)
                return error_msg
            
            # Format results
            output = f"Query executed successfully.\n"
            if result.get("rows"):
                output += f"Rows returned: {len(result['rows'])}\n"
                output += f"Columns: {result.get('columns', [])}\n\n"
                for row in result["rows"][:20]:  # Limit to 20 rows
                    output += f"  {row}\n"
                if len(result["rows"]) > 20:
                    output += f"  ... ({len(result['rows']) - 20} more rows)\n"
            else:
                output += f"Rows affected: {result.get('rowcount', 0)}\n"
            
            if _current_agent:
                _current_agent._log_tool_call("db_query", {"db_type": db_type})
                _current_agent._log_tool_result("db_query", f"Query completed, {len(result.get('rows', []))} rows", True)
            
            return output
            
        except Exception as e:
            error_msg = f"Error executing database query: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("db_query", {"db_type": db_type})
                _current_agent._log_tool_result("db_query", error_msg, False)
            return error_msg


async def _execute_sqlite(db_path: str, query: str) -> Dict[str, Any]:
    """Execute SQLite query."""
    try:
        import sqlite3
    except ImportError:
        return {"error": "sqlite3 not available"}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(query)
        
        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.close()
            return {"rows": rows, "columns": columns, "rowcount": len(rows)}
        else:
            rowcount = cursor.rowcount
            conn.commit()
            conn.close()
            return {"rows": [], "rowcount": rowcount}
    except Exception as e:
        return {"error": str(e)}


async def _execute_postgresql(connection_string: str, query: str) -> Dict[str, Any]:
    """Execute PostgreSQL query."""
    try:
        import psycopg2
    except ImportError:
        return {"error": "psycopg2 not installed. Run: pip install psycopg2-binary"}
    
    try:
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        cursor.execute(query)
        
        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.close()
            return {"rows": rows, "columns": columns, "rowcount": len(rows)}
        else:
            rowcount = cursor.rowcount
            conn.commit()
            conn.close()
            return {"rows": [], "rowcount": rowcount}
    except Exception as e:
        return {"error": str(e)}


async def _execute_mysql(connection_string: str, query: str) -> Dict[str, Any]:
    """Execute MySQL query."""
    try:
        import mysql.connector
    except ImportError:
        return {"error": "mysql-connector-python not installed. Run: pip install mysql-connector-python"}
    
    try:
        conn = mysql.connector.connect(**_parse_mysql_connection_string(connection_string))
        cursor = conn.cursor()
        cursor.execute(query)
        
        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.close()
            return {"rows": rows, "columns": columns, "rowcount": len(rows)}
        else:
            rowcount = cursor.rowcount
            conn.commit()
            conn.close()
            return {"rows": [], "rowcount": rowcount}
    except Exception as e:
        return {"error": str(e)}


def _parse_mysql_connection_string(conn_str: str) -> Dict[str, str]:
    """Parse MySQL connection string into parameters."""
    # Simple parsing for mysql://user:pass@host:port/database format
    if conn_str.startswith("mysql://"):
        conn_str = conn_str[8:]
    
    parts = conn_str.split("/")
    if len(parts) < 2:
        return {}
    
    database = parts[-1]
    host_part = parts[0]
    
    auth_host = host_part.split("@")
    if len(auth_host) == 2:
        auth = auth_host[0]
        host = auth_host[1]
        user_pass = auth.split(":")
        user = user_pass[0] if len(user_pass) > 0 else ""
        password = user_pass[1] if len(user_pass) > 1 else ""
    else:
        user = ""
        password = ""
        host = auth_host[0]
    
    host_port = host.split(":")
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 3306
    
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "database": database
    }


async def db_schema_tool(ctx: RunContext, db_type: str, connection_string: str) -> str:
    """Get database schema information (tables, columns, indexes)."""
    with tracer.start_as_current_span("db_schema_tool") as span:
        span.set_attribute("db_type", db_type)
        
        try:
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )
            
            # Schema query is read-only, always allowed
            if format_tool_call:
                format_tool_call("db_schema", {"db_type": db_type})
            
            # Get schema based on database type
            if db_type == "sqlite":
                query = "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
                result = await _execute_sqlite(connection_string, query)
            elif db_type == "postgresql":
                query = """
                    SELECT table_name, column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                """
                result = await _execute_postgresql(connection_string, query)
            elif db_type == "mysql":
                query = """
                    SELECT table_name, column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                    ORDER BY table_name, ordinal_position
                """
                result = await _execute_mysql(connection_string, query)
            else:
                error_msg = f"Unsupported database type: {db_type}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("db_schema", {"db_type": db_type})
                    _current_agent._log_tool_result("db_schema", error_msg, False)
                return error_msg
            
            if result.get("error"):
                error_msg = f"Failed to get schema: {result['error']}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("db_schema", {"db_type": db_type})
                    _current_agent._log_tool_result("db_schema", error_msg, False)
                return error_msg
            
            # Format schema output
            output = f"Database Schema ({db_type}):\n\n"
            if result.get("rows"):
                current_table = None
                for row in result["rows"]:
                    if db_type == "sqlite":
                        table_name = row[0]
                        sql = row[1]
                        output += f"Table: {table_name}\n"
                        output += f"  SQL: {sql}\n\n"
                    else:
                        table_name = row[0]
                        if table_name != current_table:
                            current_table = table_name
                            output += f"Table: {table_name}\n"
                        column_name = row[1]
                        data_type = row[2]
                        is_nullable = row[3]
                        output += f"  - {column_name}: {data_type} (nullable: {is_nullable})\n"
                output += "\n"
            else:
                output += "No tables found.\n"
            
            if _current_agent:
                _current_agent._log_tool_call("db_schema", {"db_type": db_type})
                _current_agent._log_tool_result("db_schema", f"Retrieved schema for {len(result.get('rows', []))} items", True)
            
            return output
            
        except Exception as e:
            error_msg = f"Error getting database schema: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("db_schema", {"db_type": db_type})
                _current_agent._log_tool_result("db_schema", error_msg, False)
            return error_msg


async def db_migrate_tool(ctx: RunContext, db_type: str, connection_string: str, migration_sql: str, dry_run: bool = True) -> str:
    """Execute database migration SQL. Requires write permission. Dry-run by default.
    
    Args:
        db_type: Database type (sqlite, postgresql, mysql)
        connection_string: Database connection string or file path for SQLite
        migration_sql: SQL migration script to execute
        dry_run: If True, shows what would be executed without running it (default: True)
    """
    with tracer.start_as_current_span("db_migrate_tool") as span:
        span.set_attribute("db_type", db_type)
        span.set_attribute("dry_run", dry_run)
        
        try:
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )
            
            # Migration is a write operation, check permissions
            if not permissions.check_access(connection_string, PermissionAction.WRITE, mode):
                error_msg = f"Permission denied: database migration requires write access to {connection_string}"
                span.set_attribute("access", "denied")
                if _current_agent:
                    _current_agent._log_tool_call("db_migrate", {"db_type": db_type})
                    _current_agent._log_tool_result("db_migrate", error_msg, False)
                return error_msg
            
            if format_tool_call:
                format_tool_call("db_migrate", {"db_type": db_type, "dry_run": dry_run})
            
            if dry_run:
                output = f"DRY RUN - Migration SQL (not executed):\n\n{migration_sql}\n\n"
                output += "To execute this migration, set dry_run=False and ensure you have write permissions."
                if _current_agent:
                    _current_agent._log_tool_call("db_migrate", {"db_type": db_type})
                    _current_agent._log_tool_result("db_migrate", "Dry run completed", True)
                return output
            
            # Execute migration based on database type
            if db_type == "sqlite":
                result = await _execute_sqlite(connection_string, migration_sql)
            elif db_type == "postgresql":
                result = await _execute_postgresql(connection_string, migration_sql)
            elif db_type == "mysql":
                result = await _execute_mysql(connection_string, migration_sql)
            else:
                error_msg = f"Unsupported database type: {db_type}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("db_migrate", {"db_type": db_type})
                    _current_agent._log_tool_result("db_migrate", error_msg, False)
                return error_msg
            
            if result.get("error"):
                error_msg = f"Migration failed: {result['error']}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("db_migrate", {"db_type": db_type})
                    _current_agent._log_tool_result("db_migrate", error_msg, False)
                return error_msg
            
            output = f"Migration executed successfully.\n"
            output += f"Rows affected: {result.get('rowcount', 0)}\n"
            
            if _current_agent:
                _current_agent._log_tool_call("db_migrate", {"db_type": db_type})
                _current_agent._log_tool_result("db_migrate", "Migration completed", True)
            
            return output
            
        except Exception as e:
            error_msg = f"Error executing migration: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("db_migrate", {"db_type": db_type})
                _current_agent._log_tool_result("db_migrate", error_msg, False)
            return error_msg
