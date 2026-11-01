# ZemaxMCP

ZemaxMCP is a distributable MCP server for Ansys Zemax OpticStudio. The supported release is OpticStudio 2024 R2. Supporting another release is a separate change.

## Decisions

Lasting choices are recorded in `docs/adr`. Read the accepted records before changing the interface, the process model, or the external behavior. Add a new record to reverse an accepted decision.

## Development

Use the uv environment in `.venv`. Keep the server able to find OpticStudio on a user's machine. A machine-specific installation path does not belong in the project.

Write [Sphinx-style](https://www.sphinx-doc.org/en/master/usage/restructuredtext/domains.html#info-field-lists) docstrings for public classes, functions, and methods. Document public fields and module-level variables with a `#:` comment and a Python type hint. Document `__init__` parameters on the class. Dunder methods do not get docstrings.

Prefer public attributes, classes, functions, and methods. Use a non-public name only when other code must not touch it. For example, the ZOS-API application object and the methods that use it stay non-public, because they can be used only on the thread that created the application.

Write commit messages with [Conventional Commits](https://www.conventionalcommits.org/).
