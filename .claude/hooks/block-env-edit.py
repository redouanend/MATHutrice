#!/usr/bin/env python3
"""PreToolUse hook: refuse any Edit/Write/MultiEdit targeting the project's
.env or .env.* file at the repository root.

Reads the hook payload as JSON on stdin. Exit 2 = block the tool call and feed
stderr back to the agent. Any other exit = allow.
"""
import json
import os
import sys


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0  # not our problem, don't block on malformed input

    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path:
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    abs_path = path if os.path.isabs(path) else os.path.join(project_dir, path)
    abs_path = os.path.normpath(abs_path)

    name = os.path.basename(abs_path)
    at_root = os.path.dirname(abs_path) == os.path.normpath(project_dir)
    is_env = name == ".env" or name.startswith(".env.")

    if is_env and at_root:
        sys.stderr.write(
            "BLOCKED by PreToolUse hook: the project's .env file is off-limits.\n"
            f"  Refused path: {abs_path}\n"
            "  Absolute rule (Lab 1), zero exception: the agent never modifies or\n"
            "  commits .env or .env.* . Environment secrets are edited by a human,\n"
            "  by hand, outside the agent.\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
