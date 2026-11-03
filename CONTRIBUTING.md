# Contributing

ZayMCP is a distributable MCP server for Ansys Zemax OpticStudio 2024 R2. This file describes how to set up a working copy and how to prepare a change.

## Development environment

Python 3.12 or newer is required. The project environment is managed with [uv](https://docs.astral.sh/uv/) and lives in `.venv`. To setup the virtual environment:

```bash
uv sync
```

Use that environment for development. A machine-specific OpticStudio installation path does not belong in the project. When Zemax's helper cannot find the installation, set `OPTICSTUDIO_DIRECTORY` to the installation directory on your machine.

## Checking a change

The server connects to an OpticStudio window that is already waiting on Interactive Extension.

An MCP host launches the server with:

```bash
uv run zaymcp
```

Check a change by calling the affected tool from a host attached to that session.

## Architecture decisions

Lasting choices are recorded in [docs/adr](docs/adr). Read the accepted records before changing the interface, the process model, or the external behavior. Add a new record to reverse an accepted decision. See [docs/adr/README.md](docs/adr/README.md) for more details.

## Source

A feature uses the same path under `tools` and `zosapi`. The path follows the ribbon group, and the leaf is the window, dialog, or analysis the user opens. The connection and the STA thread stay in `zosapi/session.py`. The shared read and write model used by the editors stays in `zosapi/model`. A leaf tool module imports the module-level server and decorates it.

Write [Sphinx-style](https://www.sphinx-doc.org/en/master/usage/restructuredtext/domains.html#info-field-lists) docstrings for public classes, functions, and methods. Document public fields and module-level variables with a `#:` comment and a Python type hint. Document `__init__` parameters on the class. Dunder methods do not get docstrings.

Pass an MCP tool description as the `description` argument of `@server.tool()`. Use one sentence, or one paragraph when the tool is complex, and use Markdown when that description needs formatting. The docstring still documents inputs and outputs; it is not the description sent to the host.

Prefer public attributes, classes, functions, and methods. Use a non-public name only when other code must not touch it. For example, the ZOS-API application object and the methods that use it stay non-public, because they can be used only on the thread that created the application.

## Commits

Write commit messages with [Conventional Commits](https://www.conventionalcommits.org/).

## Submitting a change

Open a pull request. Describe what changed and how you checked it against an OpticStudio 2024 R2 session.
