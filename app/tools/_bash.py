"""Bash command tool handler."""

import asyncio


async def handle_run_command(arguments: dict) -> str:
    command = arguments.get("command", "").strip()
    if not command:
        return "Error: command is required."
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode(errors="replace").strip()
        if len(output) > 4000:
            output = output[:4000] + "\n... (truncated)"
        return (
            output
            if output
            else f"Command exited with code {proc.returncode} (no output)."
        )
    except asyncio.TimeoutError:
        proc.kill()
        return "Error: command timed out after 30 seconds."
    except Exception as e:
        return f"Error running command: {e}"
