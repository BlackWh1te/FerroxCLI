"""Structured Planning Engine for Ferrox - Devin-parity feature
Auto-generates step-by-step plans for complex tasks using pydantic-ai
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskStep(BaseModel):
    """A single step in a project plan"""

    id: int
    description: str
    status: str = "pending"  # pending, in_progress, completed, failed
    result: Optional[str] = None


class ProjectPlan(BaseModel):
    """A complete project plan with steps"""

    goal: str
    steps: list[TaskStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    current_step: int = 0


# Global current plan
_current_plan: Optional[ProjectPlan] = None


def get_current_plan() -> Optional[ProjectPlan]:
    """Get the current active plan."""
    return _current_plan


def set_current_plan(plan: ProjectPlan):
    """Set the current active plan."""
    global _current_plan
    _current_plan = plan


def clear_current_plan():
    """Clear the current plan."""
    global _current_plan
    _current_plan = None


async def generate_plan(task_description: str) -> ProjectPlan:
    """
    Generate a structured plan from a task description using pydantic-ai.

    This uses pydantic-ai's structured output to generate a plan
    that can be saved to PLAN.md and executed step-by-step.
    """
    from pydantic_ai import Agent

    planning_agent = Agent(
        model="openai:gpt-4o",
        system_prompt="""You are a project planner. Break down the user's request into small, executable technical steps.

Guidelines:
- Break complex tasks into 3-8 clear steps
- Each step should be actionable and testable
- Order steps logically (setup before execution, tests after implementation)
- Use technical language appropriate for an AI engineering assistant
- Output ONLY a JSON plan with the structure: {"goal": "...", "steps": [{"id": 1, "description": "..."}, ...]}

Example:
User: "Build a todo app"
Output: {"goal": "Build a todo app", "steps": [{"id": 1, "description": "Create project structure and package.json"}, {"id": 2, "description": "Implement HTML/CSS UI with input and list"}, {"id": 3, "description": "Add JavaScript for CRUD operations"}, {"id": 4, "description": "Add local storage persistence"}, {"id": 5, "description": "Test the application"}]}""",
    )

    try:
        # Run with structured output expectation
        result = await planning_agent.run(
            f"Create a plan for: {task_description}\n\nRespond ONLY with JSON in the format: {{'goal': '...', 'steps': [{{'id': 1, 'description': '...'}}, ...]}}"
        )

        # Parse the result to create ProjectPlan
        result_text = str(result)

        # Simple JSON parsing (in production, use proper JSON parsing)
        import json
        import re

        # Try to extract JSON from the response
        json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
        if json_match:
            plan_data = json.loads(json_match.group())

            steps = [
                TaskStep(id=s["id"], description=s["description"])
                for s in plan_data.get("steps", [])
            ]

            plan = ProjectPlan(goal=plan_data.get("goal", task_description), steps=steps)

            set_current_plan(plan)
            return plan
        else:
            # Fallback: create a simple plan
            plan = ProjectPlan(
                goal=task_description,
                steps=[
                    TaskStep(id=1, description="Analyze requirements"),
                    TaskStep(id=2, description="Implement solution"),
                    TaskStep(id=3, description="Test and verify"),
                ],
            )
            set_current_plan(plan)
            return plan

    except Exception:
        # Fallback on error
        plan = ProjectPlan(
            goal=task_description,
            steps=[
                TaskStep(id=1, description=f"Analyze: {task_description}"),
                TaskStep(id=2, description="Implement the solution"),
                TaskStep(id=3, description="Verify the result"),
            ],
        )
        set_current_plan(plan)
        return plan


def save_plan_to_file(plan: ProjectPlan, filepath: str = "PLAN.md") -> str:
    """Save a plan to a markdown file."""
    content = f"# Plan: {plan.goal}\n\n"
    content += f"Created: {plan.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    content += "## Steps\n\n"

    for step in plan.steps:
        status_icon = {"pending": "⬜", "in_progress": "🔄", "completed": "✅", "failed": "❌"}.get(
            step.status, "⬜"
        )

        content += f"- {status_icon} **{step.id}.** {step.description}"
        if step.result:
            content += f"\n  - Result: {step.result[:100]}..."
        content += "\n"

    with open(filepath, "w") as f:
        f.write(content)

    return filepath


def get_plan_status() -> str:
    """Get a string representation of the current plan status."""
    plan = get_current_plan()

    if not plan:
        return "No active plan. Use /plan <task> to create one."

    completed = sum(1 for s in plan.steps if s.status == "completed")
    total = len(plan.steps)

    output = f"📋 Plan: {plan.goal}\n"
    output += f"Progress: {completed}/{total} steps completed\n\n"

    for step in plan.steps:
        status_icon = {"pending": "⬜", "in_progress": "🔄", "completed": "✅", "failed": "❌"}.get(
            step.status, "⬜"
        )

        current_marker = "👉 " if step.id == plan.current_step + 1 else "   "
        output += f"{current_marker}{status_icon} {step.id}. {step.description}\n"

    return output


def execute_next_step() -> Optional[TaskStep]:
    """Move to the next step in the plan."""
    plan = get_current_plan()

    if not plan:
        return None

    if plan.current_step >= len(plan.steps):
        return None

    # Mark current step as in progress
    step = plan.steps[plan.current_step]
    step.status = "in_progress"

    return step


def complete_step(result: str):
    """Mark the current step as completed with result."""
    plan = get_current_plan()

    if not plan or plan.current_step >= len(plan.steps):
        return

    step = plan.steps[plan.current_step]
    step.status = "completed"
    step.result = result

    # Move to next step
    plan.current_step += 1


def fail_step(error: str):
    """Mark the current step as failed."""
    plan = get_current_plan()

    if not plan or plan.current_step >= len(plan.steps):
        return

    step = plan.steps[plan.current_step]
    step.status = "failed"
    step.result = error


def jump_to_step(step_num: int) -> Optional[TaskStep]:
    """Jump to a specific step in the plan."""
    plan = get_current_plan()

    if not plan:
        return None

    if step_num < 1 or step_num > len(plan.steps):
        return None

    plan.current_step = step_num - 1

    step = plan.steps[plan.current_step]
    step.status = "in_progress"

    return step
