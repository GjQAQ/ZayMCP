# ZayMCP

An MCP server for Ansys Zemax OpticStudio 2024 R2.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
![OpticStudio 2024 R2](https://img.shields.io/badge/OpticStudio-2024%20R2-555555)

> **Unofficial project.** ZayMCP is an independent project. It is **not** developed, maintained, endorsed, or affiliated with Ansys or Zemax, and it does **not** represent Ansys Zemax OpticStudio or its publisher. “Ansys”, “Zemax”, and “OpticStudio” are trademarks of their respective owners, used here only to identify the product this server connects to.

## Requirements

- Windows
- Ansys Zemax OpticStudio 2024 R2
- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

## Quick start

### Install

The package uses the Windows registry and runs only on Windows.

```bash
uv tool install zaymcp
```

### Configure the MCP server

Register the server with the host. `OPTICSTUDIO_DIRECTORY` is the directory that contains `OpticStudio.exe`. The server uses it when Zemax's helper cannot find the installation.

```json
{
  "mcpServers": {
    "zaymcp": {
      "command": "uvx",
      "args": ["zaymcp"],
      "env": {
        "OPTICSTUDIO_DIRECTORY": "<path-to-OpticStudio>"
      }
    }
  }
}
```

### Open Interactive Extension

In OpticStudio, open **Programming → ZOS-API.NET Applications → Interactive Extension**. A dialog opens and OpticStudio waits for this server. Only one external program can be connected at a time. Leave the dialog open before the host starts the server.

## Example

[examples/001-simple-singlet.md](examples/001-simple-singlet.md) is a complete task: design a positive N-BK7 singlet, from a new lens through local optimization.

## Tools

Each tool's arguments and return fields travel with the tool schema the host receives.

<details>
<summary>Session</summary>

| Tool | Description |
| --- | --- |
| `get_opticstudio_version` | Return the product version, license, and connection details. |

</details>

<details>
<summary>File</summary>

| Tool | Description |
| --- | --- |
| `new_lens` | Replace the open lens with a new lens. Unsaved changes stay unless you discard them. |
| `get_lens_metadata` | Return the lens path, title, mode, and whether the window has unsaved changes. |
| `save_lens` | Save the current file, or save it to a new path. |

</details>

<details>
<summary>Setup</summary>

| Tool | Description |
| --- | --- |
| `get_system_settings` | Read one System Explorer group: units, aperture, fields, wavelengths, environment, polarization, or ray aiming. |
| `set_system_settings` | Change keys in one of those groups. |
| `set_system_rows` | Change, add, or remove a field point or wavelength, or choose the primary wavelength. |
| `get_lens_data` | Read the Lens Data Editor, or one surface. |
| `set_lens_rows` | Change, insert, or remove one surface. |
| `get_multi_configuration` | Read the Multi-Configuration Editor, or one operand. |
| `set_multi_configuration_rows` | Change an operand or a configuration, including which configuration is current. |

</details>

<details>
<summary>Optimize</summary>

| Tool | Description |
| --- | --- |
| `get_merit_function` | Read the Merit Function Editor, or one operand. |
| `set_merit_rows` | Change, insert, or remove one operand. |
| `calculate_merit_function` | Calculate the merit function. |
| `apply_optimization_wizard` | Apply the Optimization Wizard and return the operands it creates. |
| `run_local_optimization` | Run local optimization and return the merit function before and after. |

</details>

<details>
<summary>Analyze</summary>

| Tool | Description |
| --- | --- |
| `get_first_order` | Return effective focal length, entrance pupil diameter, F-numbers, and total length. |
| `get_single_ray_trace` | Trace one ray and return the Single Ray Trace table. |

</details>

## Connection

A host launches this server against the OpticStudio window that is waiting on Interactive Extension. The tools work on the lens open in that window, and the window stays on screen. The connection lasts for the life of the server process.

When OpticStudio cannot answer a call, the server closes the connection. The next call opens a new one, which needs the Interactive Extension dialog to be waiting again. **Auto Close on Disconnect** is on by default, so the dialog closes when the connection ends. Open Interactive Extension again before the next session. Stopping the host closes the connection the same way.

## Development

Clone the repository and create the environment:

```bash
git clone https://github.com/GjQAQ/ZayMCP.git
cd ZayMCP
uv sync
```

To run this checkout instead of the published package, point the host at it:

```json
{
  "mcpServers": {
    "zaymcp-dev": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "<path-to-checkout>",
        "zaymcp"
      ],
      "env": {
        "OPTICSTUDIO_DIRECTORY": "<path-to-OpticStudio>"
      }
    }
  }
}
```

Development conventions are in [CONTRIBUTING.md](CONTRIBUTING.md). Lasting decisions are recorded in [docs/adr](docs/adr).

## License

[MIT](LICENSE) © 2026 Jiaqi Guo
