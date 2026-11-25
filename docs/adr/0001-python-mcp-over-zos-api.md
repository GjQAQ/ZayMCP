# 0001. Use a Python MCP server over ZOS-API

- Status: Accepted
- Date: 2026-10-26

## Context

Currently the supported release is OpticStudio 2024 R2. For that release, the external programming interface is ZOS-API: a COM interface built on .NET. Official templates exist for C#, C++, Mathematica, MATLAB, and Python. ZPL runs only inside OpticStudio. The server is a long-running external process that drives an already open lens and user interface. The primary MCP ecosystem is the Python SDK.

## Decision

Implement the server in Python with the official MCP SDK (`mcp`, stdio). Load ZOS-API through the Python template shipped with Zemax. Connect with Interactive Extension by default, and use Standalone for headless batch work. Serialize every ZOS-API call onto one STA thread.

## Considered options

- C# or C++ as the server. These bind more tightly to ZOS-API, but MCP examples, Cursor configuration, and debugging are more direct in Python. A User Extension must also be an executable that OpticStudio launches, which is the opposite of the MCP process model.
- MATLAB or Mathematica. Both have official Interactive Extension templates, but neither is the implementation language for an MCP server.
- ZPL. It can only run macros inside OpticStudio and cannot serve as an external API.

## Consequences

- The user opens Interactive Extension in OpticStudio first. The server then connects to that session by instance number. Only one external program can be connected at a time.
- Standalone launches its own UI-less instance. At most one OpticStudio instance may already be open, or the license limit applies.
- ZOS-API calls cannot be made directly from individual async MCP requests. They stay on a dedicated STA thread.
- The server is built against the OpticStudio 2024 R2 ZOS-API. Supporting another release is a separate change.
