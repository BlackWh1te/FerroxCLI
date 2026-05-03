
from pydantic_ai import Agent, RunContext

from ..permissions import PermissionAction, PermissionEngine
from ..tools import execute_tool

# Initialize components
permission_engine = PermissionEngine()

# Initialize the agent
# Note: In a real scenario, we'd pull the provider/model from FerroxConfig
agent = Agent(
    model="openai:gpt-4o",  # Placeholder for dynamic model
    system_prompt="You are Ferrox, a secure AI engineering assistant.",
)


@agent.tool
async def read_file(ctx: RunContext, path: str) -> str:
    """Read a file if permitted."""
    # Integrate existing PermissionEngine
    if not permission_engine.check_access(path, PermissionAction.READ, mode=None):
        return "Error: Access denied by PermissionEngine."

    return execute_tool("read_file", {"file_path": path})


@agent.tool
async def write_file(ctx: RunContext, path: str, content: str) -> str:
    """Write to a file if permitted."""
    if not permission_engine.check_access(path, PermissionAction.WRITE, mode=None):
        return "Error: Access denied by PermissionEngine."

    return execute_tool("write_file", {"file_path": path, "content": content})


async def run_example():
    """Example usage of the Pydantic-AI agent loop."""
    result = await agent.run("Read ferrox/cli.py and summarize it.")
    print(result.data)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_example())
