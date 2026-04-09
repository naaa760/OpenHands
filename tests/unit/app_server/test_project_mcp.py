"""Tests for project-scoped .mcp.json loading."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from openhands.app_server.app_conversation.project_mcp import (
    merge_project_mcp_into_flat_servers,
)
from openhands.sdk.workspace.models import FileOperationResult
from openhands.sdk.workspace.remote.async_remote_workspace import AsyncRemoteWorkspace


@pytest.mark.asyncio
async def test_merge_skips_when_trust_false():
    mcp_servers: dict = {'default': {'url': 'u'}}
    remote = AsyncMock(spec=AsyncRemoteWorkspace)
    await merge_project_mcp_into_flat_servers(
        mcp_servers, remote, '/workspace', False
    )
    assert list(mcp_servers.keys()) == ['default']
    remote.file_download.assert_not_called()


@pytest.mark.asyncio
async def test_merge_skips_without_remote():
    mcp_servers: dict = {}
    await merge_project_mcp_into_flat_servers(
        mcp_servers, None, '/workspace', True
    )
    assert mcp_servers == {}


@pytest.mark.asyncio
async def test_merge_loads_root_then_openhands_overlay():
    root_cfg = {
        'mcpServers': {
            'shared': {'url': 'http://root/shared', 'transport': 'sse'},
            'root_only': {'url': 'http://root', 'transport': 'sse'},
        }
    }
    oh_cfg = {
        'mcpServers': {
            'shared': {'url': 'http://oh/shared', 'transport': 'sse'},
            'oh_only': {'url': 'http://oh', 'transport': 'sse'},
        }
    }

    paths_order: list[Path] = []

    async def fake_download(src: str, dst: str) -> FileOperationResult:
        paths_order.append(Path(src))
        p = Path(src)
        if p.name == '.mcp.json' and '.openhands' not in str(p):
            body = json.dumps(root_cfg)
        elif '.openhands' in str(p):
            body = json.dumps(oh_cfg)
        else:
            body = '{}'
        Path(dst).write_text(body, encoding='utf-8')
        return FileOperationResult(
            success=True,
            source_path=src,
            destination_path=dst,
            file_size=len(body.encode()),
        )

    remote = AsyncMock(spec=AsyncRemoteWorkspace)
    remote.file_download = AsyncMock(side_effect=fake_download)

    mcp_servers: dict = {}
    await merge_project_mcp_into_flat_servers(
        mcp_servers, remote, '/workspace/proj', True
    )

    assert mcp_servers['root_only']['url'] == 'http://root'
    assert mcp_servers['oh_only']['url'] == 'http://oh'
    assert mcp_servers['shared']['url'] == 'http://oh/shared'


