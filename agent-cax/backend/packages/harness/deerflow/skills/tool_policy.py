import logging
from typing import Protocol

from deerflow.skills.types import Skill

logger = logging.getLogger(__name__)


class NamedTool(Protocol):
    name: str


def allowed_tool_names_for_skills(skills: list[Skill]) -> set[str] | None:
    """Return the union of explicit skill allowed-tools declarations.

    None means legacy allow-all behavior. It is returned only when no loaded
    skill declares allowed-tools. Once any skill declares the field, legacy
    skills without the field contribute no tools instead of disabling the
    explicit restrictions from other skills.
    """
    if not skills:
        return None

    allowed: set[str] = set()
    has_explicit_declaration = False
    for skill in skills:
        if skill.allowed_tools is None:
            continue
        has_explicit_declaration = True
        if not skill.allowed_tools:
            logger.info("Skill %s declared empty allowed-tools", skill.name)
        allowed.update(skill.allowed_tools)

    if not has_explicit_declaration:
        return None
    return allowed


def _tool_name_matches(tool_name: str, allowed: set[str]) -> bool:
    """Check if a tool name matches the allowed list.

    Supports exact match and prefix wildcard with trailing '*':
    - "read_file" matches only "read_file"
    - "cad_script_*" matches "cad_script_run_scripts", "cad_script_list_files", etc.
    """
    for pattern in allowed:
        if pattern.endswith("*"):
            # Prefix wildcard: "cad_script_*" matches "cad_script_*" prefix
            prefix = pattern[:-1]
            if tool_name.startswith(prefix):
                return True
        elif tool_name == pattern:
            return True
    return False


def filter_tools_by_skill_allowed_tools[ToolT: NamedTool](tools: list[ToolT], skills: list[Skill]) -> list[ToolT]:
    allowed = allowed_tool_names_for_skills(skills)
    if allowed is None:
        return tools

    return [tool for tool in tools if _tool_name_matches(tool.name, allowed)]
