"""Multi-file editing engine for Ferrox agent.

Provides atomic multi-file transactions, dependency-aware editing,
refactoring operations, and preview mode with diff visualization.
"""

import os
import difflib
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# Import tracer
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

# Import _current_agent
try:
    from ferrox.agent.orchestrator import _current_agent
except ImportError:
    _current_agent = None


@dataclass
class FileEdit:
    """A single file edit operation."""
    path: str
    original_content: str
    new_content: str
    operation: str  # "create", "update", "delete"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class EditTransaction:
    """A transaction of multiple file edits."""
    id: str
    edits: List[FileEdit] = field(default_factory=list)
    status: str = "pending"  # pending, applied, rolled_back
    created_at: str = field(default_factory=lambda: datetime.now().isoformat)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MultiFileEditor:
    """Manages atomic multi-file editing operations."""
    
    def __init__(self):
        """Initialize the multi-file editor."""
        self.current_transaction: Optional[EditTransaction] = None
        self.transaction_history: List[EditTransaction] = []
        self.backup_dir = Path.home() / ".ferrox" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def begin_transaction(self, transaction_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Begin a new transaction.
        
        Args:
            transaction_id: Unique identifier for the transaction
            metadata: Optional metadata about the transaction
        
        Returns:
            Transaction ID
        """
        with tracer.start_as_current_span("multi_edit_begin_transaction") as span:
            span.set_attribute("transaction_id", transaction_id)
            
            if self.current_transaction:
                raise Exception("Transaction already in progress. Commit or rollback first.")
            
            self.current_transaction = EditTransaction(
                id=transaction_id,
                metadata=metadata or {}
            )
            
            return transaction_id
    
    def add_edit(self, path: str, new_content: str, operation: str = "update") -> None:
        """Add an edit to the current transaction.
        
        Args:
            path: File path
            new_content: New file content
            operation: Operation type ("create", "update", "delete")
        """
        if not self.current_transaction:
            raise Exception("No transaction in progress. Call begin_transaction first.")
        
        with tracer.start_as_current_span("multi_edit_add_edit") as span:
            span.set_attribute("path", path)
            span.set_attribute("operation", operation)
            
            # Read original content if file exists
            original_content = ""
            if Path(path).exists():
                with open(path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
            
            edit = FileEdit(
                path=path,
                original_content=original_content,
                new_content=new_content,
                operation=operation
            )
            
            self.current_transaction.edits.append(edit)
    
    def preview_transaction(self) -> Dict[str, Any]:
        """Preview the current transaction with diffs.
        
        Returns:
            Dictionary with diff information for each edit
        """
        if not self.current_transaction:
            raise Exception("No transaction in progress.")
        
        with tracer.start_as_current_span("multi_edit_preview_transaction") as span:
            span.set_attribute("transaction_id", self.current_transaction.id)
            
            preview = {
                "transaction_id": self.current_transaction.id,
                "total_edits": len(self.current_transaction.edits),
                "edits": []
            }
            
            for edit in self.current_transaction.edits:
                diff = self._generate_diff(edit.original_content, edit.new_content, edit.path)
                preview["edits"].append({
                    "path": edit.path,
                    "operation": edit.operation,
                    "diff": diff,
                    "lines_added": diff.count("\n+") if diff else 0,
                    "lines_removed": diff.count("\n-") if diff else 0
                })
            
            return preview
    
    def _generate_diff(self, original: str, new: str, filepath: str) -> str:
        """Generate a unified diff between original and new content."""
        original_lines = original.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{filepath}",
            tofile=f"b/{filepath}",
            lineterm=""
        )
        
        return "".join(diff)
    
    def commit_transaction(self, create_backup: bool = True) -> Dict[str, Any]:
        """Apply the current transaction atomically.
        
        Args:
            create_backup: Whether to create backups before applying changes
        
        Returns:
            Result dictionary with status and details
        """
        if not self.current_transaction:
            raise Exception("No transaction in progress.")
        
        with tracer.start_as_current_span("multi_edit_commit_transaction") as span:
            span.set_attribute("transaction_id", self.current_transaction.id)
            span.set_attribute("total_edits", len(self.current_transaction.edits))
            
            result = {
                "transaction_id": self.current_transaction.id,
                "status": "success",
                "applied_edits": 0,
                "failed_edits": 0,
                "errors": []
            }
            
            # Create backup if requested
            backup_path = None
            if create_backup:
                backup_path = self._create_backup()
            
            try:
                # Apply all edits
                for edit in self.current_transaction.edits:
                    try:
                        self._apply_single_edit(edit)
                        result["applied_edits"] += 1
                    except Exception as e:
                        result["failed_edits"] += 1
                        result["errors"].append({
                            "path": edit.path,
                            "error": str(e)
                        })
                        
                        # Rollback on first error
                        if backup_path:
                            self._restore_backup(backup_path)
                        result["status"] = "partial_failure"
                        self.current_transaction.status = "partial_failure"
                        return result
                
                self.current_transaction.status = "applied"
                result["status"] = "success"
                
            except Exception as e:
                # Rollback on catastrophic error
                if backup_path:
                    self._restore_backup(backup_path)
                result["status"] = "failed"
                result["errors"].append({"error": str(e)})
                self.current_transaction.status = "failed"
            
            finally:
                # Add to history
                self.transaction_history.append(self.current_transaction)
                self.current_transaction = None
                
                # Clean up backup
                if backup_path and backup_path.exists():
                    backup_path.unlink()
            
            return result
    
    def _apply_single_edit(self, edit: FileEdit) -> None:
        """Apply a single file edit."""
        path = Path(edit.path)
        
        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if edit.operation == "delete":
            if path.exists():
                path.unlink()
        else:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(edit.new_content)
    
    def rollback_transaction(self) -> Dict[str, Any]:
        """Rollback the current transaction.
        
        Returns:
            Result dictionary
        """
        if not self.current_transaction:
            raise Exception("No transaction in progress.")
        
        with tracer.start_as_current_span("multi_edit_rollback_transaction") as span:
            span.set_attribute("transaction_id", self.current_transaction.id)
            
            result = {
                "transaction_id": self.current_transaction.id,
                "status": "rolled_back",
                "restored_files": 0
            }
            
            # Restore original content for each edit
            for edit in self.current_transaction.edits:
                try:
                    path = Path(edit.path)
                    if edit.operation == "delete":
                        # File was deleted, don't recreate
                        pass
                    else:
                        with open(path, 'w', encoding='utf-8') as f:
                            f.write(edit.original_content)
                    result["restored_files"] += 1
                except Exception as e:
                    result.setdefault("errors", []).append({
                        "path": edit.path,
                        "error": str(e)
                    })
            
            self.current_transaction.status = "rolled_back"
            self.transaction_history.append(self.current_transaction)
            self.current_transaction = None
            
            return result
    
    def _create_backup(self) -> Path:
        """Create a backup of all files in the transaction."""
        backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{backup_timestamp}.tar.gz"
        
        import tarfile
        with tarfile.open(backup_path, "w:gz") as tar:
            for edit in self.current_transaction.edits:
                path = Path(edit.path)
                if path.exists():
                    tar.add(path, arcname=path.name)
        
        return backup_path
    
    def _restore_backup(self, backup_path: Path) -> None:
        """Restore files from backup."""
        import tarfile
        with tarfile.open(backup_path, "r:gz") as tar:
            tar.extractall(self.backup_dir)
    
    def extract_function(self, source_file: str, function_name: str, target_file: str) -> Dict[str, Any]:
        """Extract a function to a new file and update imports.
        
        Args:
            source_file: Source file path
            function_name: Function name to extract
            target_file: Target file path for extracted function
        
        Returns:
            Result dictionary
        """
        with tracer.start_as_current_span("multi_edit_extract_function") as span:
            span.set_attribute("source_file", source_file)
            span.set_attribute("function_name", function_name)
            span.set_attribute("target_file", target_file)
            
            result = {
                "operation": "extract_function",
                "source_file": source_file,
                "function_name": function_name,
                "target_file": target_file,
                "status": "pending"
            }
            
            try:
                # Read source file
                with open(source_file, 'r') as f:
                    source_content = f.read()
                
                # Find function (simple regex-based approach)
                import re
                function_pattern = rf'(def {function_name}\s*\([^)]*\)\s*->[^:]*:.*?)(?=\ndef |\Z)'
                match = re.search(function_pattern, source_content, re.DOTALL)
                
                if not match:
                    result["status"] = "failed"
                    result["error"] = f"Function {function_name} not found in {source_file}"
                    return result
                
                function_code = match.group(1)
                
                # Remove function from source
                new_source_content = source_content.replace(function_code, "")
                
                # Create target file with function
                target_content = f"""# Extracted from {source_file}

{function_code}
"""
                
                # Begin transaction
                self.begin_transaction(f"extract_{function_name}")
                self.add_edit(source_file, new_source_content, "update")
                self.add_edit(target_file, target_content, "create")
                
                result["status"] = "transaction_created"
                result["transaction_id"] = self.current_transaction.id
                
            except Exception as e:
                result["status"] = "failed"
                result["error"] = str(e)
            
            return result
    
    def rename_symbol(self, file_path: str, old_name: str, new_name: str, scope: str = "file") -> Dict[str, Any]:
        """Rename a symbol (function, variable, class) across files.
        
        Args:
            file_path: File containing the symbol
            old_name: Current symbol name
            new_name: New symbol name
            scope: Scope of rename ("file" or "project")
        
        Returns:
            Result dictionary
        """
        with tracer.start_as_current_span("multi_edit_rename_symbol") as span:
            span.set_attribute("file_path", file_path)
            span.set_attribute("old_name", old_name)
            span.set_attribute("new_name", new_name)
            span.set_attribute("scope", scope)
            
            result = {
                "operation": "rename_symbol",
                "file_path": file_path,
                "old_name": old_name,
                "new_name": new_name,
                "scope": scope,
                "status": "pending",
                "affected_files": []
            }
            
            try:
                # For now, implement file-scope rename
                if scope == "file":
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Simple string replacement (in production, use AST)
                    import re
                    # Replace whole words only
                    pattern = r'\b' + re.escape(old_name) + r'\b'
                    new_content = re.sub(pattern, new_name, content)
                    
                    if new_content == content:
                        result["status"] = "no_changes"
                        result["message"] = f"Symbol '{old_name}' not found in file"
                        return result
                    
                    self.begin_transaction(f"rename_{old_name}_to_{new_name}")
                    self.add_edit(file_path, new_content, "update")
                    
                    result["status"] = "transaction_created"
                    result["transaction_id"] = self.current_transaction.id
                    result["affected_files"] = [file_path]
                
                else:
                    result["status"] = "not_implemented"
                    result["message"] = "Project-scope rename not yet implemented"
                
            except Exception as e:
                result["status"] = "failed"
                result["error"] = str(e)
            
            return result
    
    def move_file(self, old_path: str, new_path: str, update_imports: bool = True) -> Dict[str, Any]:
        """Move a file to a new location and update imports.
        
        Args:
            old_path: Current file path
            new_path: New file path
            update_imports: Whether to update imports in other files
        
        Returns:
            Result dictionary
        """
        with tracer.start_as_current_span("multi_edit_move_file") as span:
            span.set_attribute("old_path", old_path)
            span.set_attribute("new_path", new_path)
            span.set_attribute("update_imports", update_imports)
            
            result = {
                "operation": "move_file",
                "old_path": old_path,
                "new_path": new_path,
                "update_imports": update_imports,
                "status": "pending"
            }
            
            try:
                if not Path(old_path).exists():
                    result["status"] = "failed"
                    result["error"] = f"Source file not found: {old_path}"
                    return result
                
                # Read original content
                with open(old_path, 'r') as f:
                    content = f.read()
                
                # Begin transaction
                self.begin_transaction(f"move_{Path(old_path).name}")
                
                # Delete old file
                self.add_edit(old_path, "", "delete")
                
                # Create new file
                self.add_edit(new_path, content, "create")
                
                result["status"] = "transaction_created"
                result["transaction_id"] = self.current_transaction.id
                
                if update_imports:
                    result["message"] = "Import updates not yet implemented"
                
            except Exception as e:
                result["status"] = "failed"
                result["error"] = str(e)
            
            return result
    
    def get_transaction_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get transaction history.
        
        Args:
            limit: Maximum number of transactions to return
        
        Returns:
            List of transaction summaries
        """
        history = self.transaction_history[-limit:]
        return [
            {
                "id": t.id,
                "status": t.status,
                "total_edits": len(t.edits),
                "created_at": t.created_at,
                "metadata": t.metadata
            }
            for t in reversed(history)
        ]
