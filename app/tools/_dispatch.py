"""Central tool call dispatcher."""

from ..config import BuiltinToolsConfig
from ._bash import handle_run_command
from ._mcp_servers import (
    handle_mcp_server_create,
    handle_mcp_server_delete,
    handle_mcp_server_edit,
    handle_mcp_server_list,
    handle_mcp_server_logs,
    handle_mcp_server_start,
    handle_mcp_server_stop,
)
from ._memory import (
    handle_memory_create,
    handle_memory_delete,
    handle_memory_edit,
    handle_memory_list,
    handle_memory_patch,
    handle_memory_read,
)
from ._state import (
    handle_state_check_time,
    handle_state_get,
    handle_state_list,
    handle_state_set,
)
from ._vector import (
    handle_vector_delete,
    handle_vector_list,
    handle_vector_save,
    handle_vector_search,
)
from ._web_search import handle_web_search


async def handle_tool_call(
    name: str,
    arguments: dict,
    *,
    animation_names: list[str],
    play_animation_fn,
    mcp_manager,
    background_names: list[str] | None = None,
    set_background_fn=None,
    builtin_tools_config: BuiltinToolsConfig | None = None,
) -> str:
    """Execute a tool call and return the result as a string."""
    if name == "get_animations":
        return f"Available animations: {', '.join(animation_names)}"

    if name == "get_backgrounds":
        if background_names:
            return f"Available backgrounds: {', '.join(background_names)}"
        return "No backgrounds available."

    if name == "play_animation":
        anim_name = arguments.get("name", "")
        if anim_name in animation_names:
            await play_animation_fn(anim_name)
            return f"Now playing animation: {anim_name}"
        else:
            return f"Unknown animation: {anim_name}. Available: {', '.join(animation_names)}"

    if name == "memory_list":
        return handle_memory_list()
    if name == "memory_create":
        return handle_memory_create(arguments)
    if name == "memory_read":
        return handle_memory_read(arguments)
    if name == "memory_edit":
        return handle_memory_edit(arguments)
    if name == "memory_delete":
        return handle_memory_delete(arguments)
    if name == "memory_patch":
        return handle_memory_patch(arguments)

    if name == "state_set":
        return handle_state_set(arguments)
    if name == "state_get":
        return handle_state_get(arguments)
    if name == "state_list":
        return handle_state_list()
    if name == "state_check_time":
        return handle_state_check_time(arguments)

    if name == "set_background" and set_background_fn and background_names:
        bg_name = arguments.get("name", "")
        if bg_name in background_names:
            await set_background_fn(bg_name)
            return f"Background changed to: {bg_name}"
        return (
            f"Unknown background: {bg_name}. Available: {', '.join(background_names)}"
        )

    if name == "web_search":
        tc = builtin_tools_config or BuiltinToolsConfig()
        return await handle_web_search(arguments, tc.web_search.brave_api_key)
    if name == "run_command":
        return await handle_run_command(arguments)

    if name == "vector_save":
        return handle_vector_save(arguments)
    if name == "vector_search":
        return handle_vector_search(arguments)
    if name == "vector_delete":
        return handle_vector_delete(arguments)
    if name == "vector_list":
        return handle_vector_list()

    if name == "mcp_server_create":
        return await handle_mcp_server_create(arguments, mcp_manager)
    if name == "mcp_server_edit":
        return await handle_mcp_server_edit(arguments, mcp_manager)
    if name == "mcp_server_delete":
        return await handle_mcp_server_delete(arguments, mcp_manager)
    if name == "mcp_server_list":
        return await handle_mcp_server_list(mcp_manager)
    if name == "mcp_server_start":
        return await handle_mcp_server_start(arguments, mcp_manager)
    if name == "mcp_server_stop":
        return await handle_mcp_server_stop(arguments, mcp_manager)
    if name == "mcp_server_logs":
        return await handle_mcp_server_logs(arguments, mcp_manager)

    if mcp_manager.has_tool(name):
        return await mcp_manager.call_tool(name, arguments)

    return f"Unknown tool: {name}"
