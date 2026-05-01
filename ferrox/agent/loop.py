import asyncio
from ..logger_new import logger
from ..tools import execute_tool
from ..fallback import FallbackEngine
from rich.console import Console

console = Console()

class AgentLoop:
    def __init__(self, fallback_engine: FallbackEngine, permission_engine):
        self.fallback_engine = fallback_engine
        self.permission_engine = permission_engine
        self.max_retries = 3

    async def execute_task_with_test_loop(self, task_description: str, test_command: str = None, cwd: str = ".") -> dict:
        """
        1. Ask AI to implement task.
        2. Apply changes.
        3. Run test_command (if provided).
        4. If fail, send error to AI and retry up to max_retries.
        """
        attempts = 0
        last_error = None
        chat_history = [{"role": "user", "content": task_description}]
        
        while attempts < self.max_retries:
            attempts += 1
            logger.info(f"--- Agent Loop Attempt {attempts}/{self.max_retries} ---")
            
            # 1. Get AI Implementation
            console.print(f"[dim]🔄 Attempt {attempts}: Generating solution...[/dim]")
            try:
                result = await self.fallback_engine.send_with_fallback(
                    messages=chat_history,
                    active_provider_id=self.fallback_engine.config.active_provider_id
                )
                
                if not result.get('success'):
                    return {"error": "AI generation failed", "details": result}
                
                ai_content = result['content']
                chat_history.append({"role": "assistant", "content": ai_content})
                
                # 3. Run Tests
                if test_command:
                    console.print(f"[dim]🧪 Running tests: {test_command}[/dim]")
                    # Use execute_tool wrapper
                    test_result_str = execute_tool("run_command", {"command": test_command, "cwd": cwd})
                    
                    # Logic to determine success - very basic parsing
                    success = "exit code: 0" in test_result_str.lower()
                    
                    if success:
                        logger.info("✅ Tests passed!")
                        return {"success": True, "message": "Task completed and verified.", "attempts": attempts}
                    else:
                        last_error = test_result_str[-1000:]
                        logger.warning(f"❌ Tests failed.")
                        console.print(f"[yellow]⚠️ Tests failed. Auto-correcting...[/yellow]")
                        
                        # Add error to history for next attempt
                        chat_history.append({
                            "role": "user", 
                            "content": f"The previous change caused tests to fail. Here is the output:\n\n{last_error}\n\nPlease fix the code."
                        })
                else:
                    return {"success": True, "message": "Task completed (no tests run).", "attempts": attempts}
                    
            except Exception as e:
                logger.error(f"Agent loop error: {e}")
                last_error = str(e)
                continue

        return {"error": f"Max retries ({self.max_retries}) reached. Last error: {last_error}", "attempts": attempts}
