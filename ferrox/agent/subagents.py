"""Subagent System for Ferrox - Devin-parity feature
Supports specialized subagents (Researcher, Coder, Reviewer) with dynamic Ollama models
"""

from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

# --- Subagent Result Models ---


class SubagentResult(BaseModel):
    """Result from a subagent execution"""

    role: str
    summary: str
    artifacts: List[str] = Field(default_factory=list)
    success: bool
    model_used: str
    error: Optional[str] = None


# --- Subagent System Prompts ---

RESEARCHER_PROMPT = """You are an expert technical researcher. Your goal is to find accurate information, 
documentation, and best practices. 

Guidelines:
- Search for relevant documentation and resources
- Provide summaries with specific links and references
- DO NOT write code - only provide research findings
- Be thorough and cite your sources
- If something is unclear, state what you don't know"""

CODER_PROMPT = """You are an expert software engineer. You write clean, efficient, and well-documented code.

Guidelines:
- Use appropriate tools to read/write files
- Follow best practices for the language/framework
- Add comments for complex logic
- Handle errors gracefully
- Write tests when appropriate
- Ask for clarification if requirements are unclear"""

REVIEWER_PROMPT = """You are a senior code reviewer. You look for bugs, security vulnerabilities, and performance issues.

Guidelines:
- Be critical and precise
- Look for common vulnerabilities (injection, auth issues)
- Check for performance bottlenecks
- Verify error handling
- Check for code smells and anti-patterns
- Suggest specific improvements"""


# --- Agent Factory Functions ---


def create_researcher_agent(model_name: str = "openai:gpt-4o") -> Agent:
    """Create a researcher subagent with the specified model."""
    return Agent(model=model_name, system_prompt=RESEARCHER_PROMPT)


def create_coder_agent(model_name: str = "openai:gpt-4o") -> Agent:
    """Create a coder subagent with the specified model."""
    return Agent(model=model_name, system_prompt=CODER_PROMPT)


def create_reviewer_agent(model_name: str = "openai:gpt-4o") -> Agent:
    """Create a reviewer subagent with the specified model."""
    return Agent(model=model_name, system_prompt=REVIEWER_PROMPT)


# --- Subagent Factory with Tools ---


def create_agent_with_tools(role: str, model_name: str) -> Agent:
    """Create a subagent with tools based on role."""
    from .tools_pydantic import (
        list_directory_tool,
        read_file_tool,
        run_command_tool,
        search_code_tool,
        write_file_tool,
    )

    if role == "researcher":
        agent = create_researcher_agent(model_name)
        # Researchers get read-only tools
        agent.tool(read_file_tool)
        agent.tool(list_directory_tool)
        agent.tool(search_code_tool)
    elif role == "coder":
        agent = create_coder_agent(model_name)
        # Coders get full tool access
        agent.tool(read_file_tool)
        agent.tool(write_file_tool)
        agent.tool(run_command_tool)
        agent.tool(list_directory_tool)
    elif role == "reviewer":
        agent = create_reviewer_agent(model_name)
        # Reviewers get read + search tools
        agent.tool(read_file_tool)
        agent.tool(list_directory_tool)
        agent.tool(search_code_tool)
    else:
        raise ValueError(f"Unknown role: {role}")

    return agent


# --- Delegation Tool ---


async def delegate_task(
    ctx: RunContext, role: str, task_description: str, model: Optional[str] = None
) -> SubagentResult:
    """
    Delegate a specific task to a specialized subagent.

    Args:
        role: 'researcher', 'coder', 'reviewer'
        task_description: The specific task for the subagent
        model: Optional. Specific model to use (e.g., 'ollama:llama3.2')
               If None, uses default from config
    """
    from ..config import load_config
    from .orchestrator import _current_agent

    # Get config for default models
    config = load_config()

    # Determine model to use
    # Priority: 1) explicit model 2) config defaults 3) fallback
    if model:
        target_model = model
    elif config and hasattr(config, "subagent_defaults") and config.subagent_defaults:
        defaults = config.subagent_defaults
        target_model = defaults.get(role, "openai:gpt-4o")
    else:
        # Fallback defaults for Ollama
        fallback_models = {
            "researcher": "ollama:llama3.2",
            "coder": "ollama:qwen2.5-coder:7b",
            "reviewer": "ollama:llama3.2",
        }
        target_model = fallback_models.get(role, "openai:gpt-4o")

    # Log delegation start
    if _current_agent:
        _current_agent._log_thought(f"Spawning {role} subagent on model: {target_model}")

    # Select and create agent
    try:
        agent = create_agent_with_tools(role, target_model)

        # Run the subagent
        result = await agent.run(task_description)

        # Log success
        if _current_agent:
            _current_agent._log_thought(f"{role} subagent completed successfully")

        return SubagentResult(
            role=role,
            summary=str(result)[:2000],  # Truncate for main context
            artifacts=[],
            success=True,
            model_used=target_model,
        )

    except Exception as e:
        # Log failure
        if _current_agent:
            _current_agent._log_thought(f"{role} subagent failed: {str(e)}")

        return SubagentResult(
            role=role,
            summary=f"Error: {str(e)}",
            artifacts=[],
            success=False,
            model_used=target_model,
            error=str(e),
        )


# --- Convenience Functions ---


async def research_task(task: str, model: Optional[str] = None) -> SubagentResult:
    """Quick wrapper for research tasks."""
    return await delegate_task(None, "researcher", task, model)


async def code_task(task: str, model: Optional[str] = None) -> SubagentResult:
    """Quick wrapper for coding tasks."""
    return await delegate_task(None, "coder", task, model)


async def review_task(task: str, model: Optional[str] = None) -> SubagentResult:
    """Quick wrapper for review tasks."""
    return await delegate_task(None, "reviewer", task, model)
