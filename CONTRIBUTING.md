# Contributing

ZayMCP is a distributable MCP server for Ansys Zemax OpticStudio 2024 R2. This file describes how to set up a working copy and how to prepare a change.

## Setup

### Environment

Python 3.12 or newer is required. The project environment is managed with [uv](https://docs.astral.sh/uv/) and lives in `.venv`. To set up the virtual environment:

```bash
uv sync
```

Use that environment for development. A machine-specific OpticStudio installation path does not belong in the project. When Zemax's helper cannot find the installation, set `OPTICSTUDIO_DIRECTORY` to the installation directory on your machine.

### Running the server

The server connects to an OpticStudio window that is already waiting on Interactive Extension.

An MCP host launches the server with:

```bash
uv run zaymcp
```

### Checking a change

Check a change by calling the affected tool from a host attached to that session.

## Decisions

Lasting choices are recorded in [docs/adr](docs/adr). Read the accepted records before changing the interface, the process model, or the external behavior. Add a new record to reverse an accepted decision. See [docs/adr/README.md](docs/adr/README.md).

## Source

### Layout

A feature uses the same path under `tools` and `zosapi`. The path follows the ribbon group, and the leaf is the window, dialog, or analysis the user opens.

The connection and the STA thread stay in `zosapi/session.py`. The shared read and write model used by the editors stays in `zosapi/model`. A leaf tool module imports the module-level server and decorates it.

### Names

Prefer public attributes, classes, functions, and methods. Use a non-public name only when other code must not touch it. For example, the ZOS-API application object and the methods that use it stay non-public, because they can be used only on the thread that created the application.

### Docstrings

Write [Sphinx-style](https://www.sphinx-doc.org/en/master/usage/restructuredtext/domains.html#info-field-lists) docstrings for public classes, functions, and methods. Document public fields and module-level variables with a `#:` comment and a Python type hint. Document `__init__` parameters on the class. Dunder methods do not get docstrings.

### Tool descriptions

Pass an MCP tool description as the `description` argument of `@server.tool()`. Use one sentence, or one paragraph when the tool is complex, and use Markdown when that description needs formatting. The docstring still documents inputs and outputs; it is not the description sent to the host.

### Editor rows

A row object contains the fields that row can be written. Omit a field when the current row does not use that column, and omit the solve that belongs to it. Reject a write of either field. State the omission, and the condition that makes the field absent, in the tool description and the docstring.

#### Unused columns

Decide that the column is unused from the editor.

- The image surface has no thickness.
- A merit operand omits `target`, `weight`, `value`, and `contribution` when that cell's `IsActive` is false.
- A lens surface omits `tce` and `tce_solve` when the TCE cell is read-only. `IsActive` stays true for that cell; a catalog glass grays it out. Air and mount surfaces keep a writable TCE cell.

#### Stored values

A column the row uses keeps its stored value. An infinite radius or thickness remains the string `Infinity`. An empty comment remains an empty string. A zero remains zero.

## Submitting a change

### Commits

Write commit messages with [Conventional Commits](https://www.conventionalcommits.org/).

### Pull requests

Open a pull request. Describe what changed and how you checked it against an OpticStudio 2024 R2 session.
