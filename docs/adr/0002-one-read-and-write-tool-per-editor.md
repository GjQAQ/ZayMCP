# 0002. Use one read tool and one write tool for each editor

- Status: Accepted
- Date: 2026-11-01

## Context

The server exposes OpticStudio editors to an MCP host. System Explorer is the first editor, and it contains several setting groups: units, aperture, fields, wavelengths, environment, polarization, and ray aiming. Lens data and the merit function are later editors of the same kind. A host receives every tool name, description, and input schema on each turn. A tool per setting, or a separate read tool and write tool for every group, grows with the number of settings. The field list then returns in each write tool's input schema.

## Decision

Expose each editor through one read tool and one write tool. System Explorer uses `get_system_settings(section)` and `set_system_settings(section, values)`. `section` names a setting group. `values` contains only the keys to change, and those keys match the object returned for that group. A group that is a list of rows is read by the same get tool. Changing a row is a separate tool.

## Considered options

- One read tool and one write tool for each setting group. The host receives every group on every turn, and each write tool repeats that group's fields in its input schema.
- Keep a read tool per group and use one write tool. Reading and writing the same editor then have different shapes.
- One tool that accepts an arbitrary ZOS-API member path. The host has no enumeration of groups, and a wrong path is an untyped string.

## Consequences

- Adding a setting group adds an enumeration value, not a new tool. Lens data and the merit function follow the same pair when they are added.
- `set_system_settings` does not change field points or the wavelength list. Those are lists of rows.
- A read-only member, such as `apodization_factor_is_used`, remains in the get result and is rejected by the set tool.
- Tool descriptions stay short. The field list stays in the docstring.
