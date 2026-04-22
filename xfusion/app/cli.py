from __future__ import annotations

from xfusion.app.settings import load_settings
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan
from xfusion.execution.command_runner import CommandRunner
from xfusion.graph.wiring import build_agent_graph
from xfusion.tools.disk import DiskTools
from xfusion.tools.process import ProcessTools
from xfusion.tools.registry import ToolRegistry
from xfusion.tools.system import SystemTools


def main() -> None:
    """XFusion Guardian CLI Entrypoint."""
    settings = load_settings()
    runner = CommandRunner()

    system_tools = SystemTools(runner)
    disk_tools = DiskTools(runner)
    process_tools = ProcessTools(runner)

    registry = ToolRegistry(system_tools, disk_tools, process_tools)

    # Detect initial environment
    env_output = system_tools.detect_os()
    initial_env = EnvironmentState.model_validate(env_output.data)

    graph = build_agent_graph(registry).compile()

    print("XFusion Guardian v0.1")
    print("Safety-aware Linux Administration Agent")
    print("-" * 40)

    state: dict[str, object] = {
        "user_input": "",
        "environment": initial_env,
        "language": "en",
        "plan": None,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "step_outputs": {},
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
        "audit_log_path": settings.audit_log_path,
    }

    while True:
        try:
            user_input = input("\n> ").strip()
            if user_input.lower() in {"exit", "quit", "bye"}:
                break
            if not user_input:
                continue

            # Reset transient state if previous plan was completed/failed/refused/aborted
            plan = state.get("plan")
            if isinstance(plan, ExecutionPlan) and plan.interaction_state in {
                "completed",
                "failed",
                "refused",
                "aborted",
            }:
                state["plan"] = None
                state["current_step_id"] = None
                state["policy_decision"] = None
                state["verification_result"] = None
                state["last_tool_output"] = None
                state["step_outputs"] = {}
                state["pending_confirmation_phrase"] = None
                state["response"] = ""

            # Update user input in state
            state["user_input"] = user_input

            # Run the graph
            state = graph.invoke(state)

            print(f"\n{state.get('response', 'No response generated.')}")

        except KeyboardInterrupt:
            print("\nAborted.")
            break
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
