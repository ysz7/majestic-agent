"""Schedule management tools — create and list cron schedules."""
from majestic.tools.registry import tool


@tool(
    name="create_schedule",
    description=(
        "Create a recurring scheduled task using natural language. "
        "Use when the user asks to run something automatically at a specific time or interval. "
        "Examples: 'every day at 8am run research', 'every Monday send briefing', 'hourly check market'. "
        "The schedule is saved and will run automatically in the background."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Natural language description of when and what to run, e.g. 'every day at 8am run research and send briefing'",
            },
        },
        "required": ["description"],
    },
)
def create_schedule(description: str) -> str:
    from majestic.cron.jobs import nl_to_schedule, add_schedule, list_schedules
    try:
        sched = nl_to_schedule(description)
        add_schedule(
            name=sched["name"],
            cron_expr=sched["cron"],
            prompt=sched.get("prompt", ""),
            delivery_target=sched.get("target", "cli"),
            parallel=sched.get("parallel", False),
            subtasks=sched.get("subtasks"),
        )
        return f"Schedule created: '{sched['name']}' — runs {sched['cron']} (cron). Use /schedule list to verify."
    except Exception as e:
        return f"Failed to create schedule: {e}"


@tool(
    name="list_schedules",
    description="List all currently configured scheduled tasks with their IDs, cron expressions, and status.",
    input_schema={"type": "object", "properties": {}},
)
def list_schedules_tool() -> str:
    from majestic.cron.jobs import list_schedules
    rows = list_schedules()
    if not rows:
        return "No schedules configured."
    lines = []
    for r in rows:
        status = "enabled" if r.get("enabled") else "disabled"
        lines.append(f"[{r['id']}] {r['name']} — {r['cron_expr']} ({status}), next: {r.get('next_run', '?')[:16]}")
    return "\n".join(lines)


@tool(
    name="delete_schedule",
    description=(
        "Delete a scheduled task by ID. "
        "Always call list_schedules first to get the correct ID, then delete by that ID. "
        "To delete all schedules, list them first and delete each ID individually."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "schedule_id": {
                "type": "integer",
                "description": "The numeric ID of the schedule to delete (from list_schedules)",
            },
        },
        "required": ["schedule_id"],
    },
)
def delete_schedule(schedule_id: int) -> str:
    from majestic.cron.jobs import remove_schedule
    ok = remove_schedule(schedule_id)
    if ok:
        return f"Schedule {schedule_id} deleted."
    return f"Schedule {schedule_id} not found."
