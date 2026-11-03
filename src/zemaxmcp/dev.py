"""Entry point for ``mcp dev``.

The CLI loads this file by path. Tool modules import ``zemaxmcp.server``, so
this file re-exports that module's server instead of creating a second one.
"""

import mcp.server

import zemaxmcp.server

__all__ = [
    'server',
]

#: MCP server loaded by ``mcp dev``.
server: mcp.server.MCPServer = zemaxmcp.server.server
