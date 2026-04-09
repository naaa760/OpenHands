"""Load project-scoped MCP configuration from .mcp.json in the workspace."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastmcp.mcp_config import MCPConfig
from openhands.sdk.context.skills.utils import expand_mcp_variables
from openhands.sdk.workspace.remote.async_remote_workspace import AsyncRemoteWorkspace

logger = logging.getLogger(__name__)


def _parse_and_validate_mcp_json(raw: str, project_dir: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('mcp config root must be a JSON object')
    variables = {
        'SKILL_ROOT': project_dir,
        'PROJECT_ROOT': project_dir,
    }
    expanded = expand_mcp_variables(data, variables)
    MCPConfig.model_validate(expanded)
    return expanded.get('mcpServers') or {}


async def _download_mcp_file(
    remote_workspace: AsyncRemoteWorkspace, absolute_path: Path
) -> str | None:
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mcp.json') as tmp:
            tmp_path = tmp.name
        result = await remote_workspace.file_download(str(absolute_path), tmp_path)
        if not result.success:
            return None
        assert tmp_path is not None
        return Path(tmp_path).read_text(encoding='utf-8')
    except Exception as e:
        logger.debug(
            'Project MCP file not loaded from %s: %s', absolute_path, e, exc_info=True
        )
        return None
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


async def merge_project_mcp_into_flat_servers(
    mcp_servers: dict[str, Any],
    remote_workspace: AsyncRemoteWorkspace | None,
    project_dir: str | None,
    trust_project_mcp: bool,
) -> None:
    """Merge servers from project .mcp.json files into ``mcp_servers`` (in place).

    Discovery (repo root ``.mcp.json`` first, then ``.openhands/.mcp.json`` overlay).
    User-level MCP merged later in the caller overrides these entries by name.

    Loads only when ``trust_project_mcp`` is true (user approved). Requires a
    remote workspace so files are read from the sandbox.
    """
    if not trust_project_mcp or not project_dir:
        return
    if remote_workspace is None:
        return

    root = Path(project_dir)
    layers: list[Path] = [
        root / '.mcp.json',
        root / '.openhands' / '.mcp.json',
    ]

    merged: dict[str, Any] = {}
    for path in layers:
        text = await _download_mcp_file(remote_workspace, path)
        if text is None:
            continue
        try:
            servers = _parse_and_validate_mcp_json(text, project_dir)
        except Exception as e:
            logger.warning(
                'Invalid project MCP config at %s: %s', path, e, exc_info=True
            )
            continue
        merged.update(servers)

    if not merged:
        return

    for name, cfg in merged.items():
        if name in mcp_servers:
            logger.info(
                "Project MCP server '%s' overrides an existing entry of the same name",
                name,
            )
        mcp_servers[name] = cfg
