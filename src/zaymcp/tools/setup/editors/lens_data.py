"""Lens Data Editor tools."""

import typing

import mcp.server.mcpserver

import zaymcp.server as mcp_server

__all__ = [
    'get_lens_data',
    'set_lens_rows',
]

# A cell solve is an object inside a column value, which is itself inside `values`.
_SolveValue = str | float | int | dict[str, str | float | int]
_CellValue = str | float | int | dict[str, _SolveValue]
_EditorValues = dict[str, str | float | bool | int | dict[str, _CellValue]]

@mcp_server.server.tool(
    description='Return the Lens Data Editor surfaces, or one surface when `surface` is given.',
)
def get_lens_data(
    ctx: mcp.server.mcpserver.Context,
    surface: int | None = None,
) -> dict[str, object]:
    """
    Return the Lens Data Editor surfaces for the lens open in the OpticStudio window.

    Pass ``surface`` to read one surface. Omit it to read every surface.

    :param surface: Surface number. 0 is the object surface. ``None`` reads every surface.
    :returns: Without ``surface``, ``surfaces``. With ``surface``, that surface.

        * **surfaces** -- One entry per surface, starting with the object surface at surface 0. Present when ``surface`` is omitted.
        * **surface_number** -- Surface number. 0 is the object surface.
        * **is_stop** -- True when the surface is the stop.
        * **type** -- Surface type, such as ``Standard`` or ``EvenAspheric``.
        * **parameters** -- Parameter columns used by ``type``. Empty when the type uses none.
        * **parameters[].column** -- Column name, such as ``Par1``.
        * **parameters[].header** -- Column title from the Lens Data Editor. This member is read-only.
        * **parameters[].value** -- Cell value. A number, or a string when the cell stores text.
        * **parameters[].solve** -- Solve on that parameter cell. The same object as ``radius_solve``.
        * **comment** -- Surface comment. Empty when the surface has no comment.
        * **radius** -- Radius of curvature, in lens units.
        * **radius_solve** -- Solve on the radius cell. ``thickness_solve``, ``material_solve``, ``coating_solve``, ``semi_diameter_solve``, ``chip_zone_solve``, ``mechanical_semi_diameter_solve``, ``conic_solve``, and ``tce_solve`` use the same object.
        * **radius_solve.type** -- ``Variable``, ``Fixed``, ``SurfacePickup``, ``FNumber``, ``Position``, ``ConfigPickup``, or ``ThermalPickup``. A type this cell does not support is rejected.
        * **radius_solve.f_number** -- F-number. Present when ``type`` is ``FNumber``.
        * **radius_solve.from_surface** -- Surface the position is measured from. Present when ``type`` is ``Position``. 0 is the object surface.
        * **radius_solve.length** -- Distance from ``from_surface``, in lens units.
        * **radius_solve.surface** -- Surface a pickup reads. Present when ``type`` is ``SurfacePickup``.
        * **radius_solve.scale** -- Pickup scale. Present when that pickup uses a scale.
        * **radius_solve.offset** -- Pickup offset. Present when that pickup uses an offset.
        * **radius_solve.column** -- Lens Data column a surface pickup reads, such as ``Thickness`` or ``Par1``. Omitted when the pickup uses the same column.
        * **radius_solve.operand** -- Operand a configuration pickup reads. Present when ``type`` is ``ConfigPickup``.
        * **radius_solve.configuration** -- Configuration a pickup reads. Present for ``ConfigPickup`` and ``ThermalPickup``.
        * **thickness** -- Thickness to the next surface, in lens units.
        * **material** -- Glass name. Empty when the surface is air.
        * **coating** -- Coating name. Empty when the surface has no coating.
        * **semi_diameter** -- Clear semi-diameter, in lens units.
        * **chip_zone** -- Chip zone, in lens units.
        * **mechanical_semi_diameter** -- Mechanical semi-diameter, in lens units.
        * **conic** -- Conic constant.
        * **tce** -- Thermal coefficient of expansion stored for the surface.
    :rtype: dict[str, object]
    :raises ValueError: ``surface`` is outside the editor.
    """

    return mcp_server.read(ctx, lambda session: session.lens_data(surface))


@mcp_server.server.tool(
    description=(
        'Change, insert, or remove one surface in the Lens Data Editor. '
        '`action` is `change`, `add`, or `remove`. '
        '`number` is the surface number, and `0` is the object surface. '
        '`add` inserts a surface at `number`. '
        '`values` uses the same fields as one surface returned by `get_lens_data`. '
        '`type` sets the surface type. '
        '`parameters` maps column names such as `Par1` to a value, or to an object with `value` and `solve`. '
        '`radius_solve` and the other cell solves use the same solve object. '
        'When type and parameters are both set, the type changes first.'
    ),
)
def set_lens_rows(
    ctx: mcp.server.mcpserver.Context,
    action: typing.Literal['change', 'add', 'remove'],
    number: int,
    values: _EditorValues | None = None,
) -> dict[str, object]:
    """
    Change, insert, or remove one Lens Data Editor surface and return the editor.

    :param action: ``change``, ``add``, or ``remove``.
    :param number: Surface number. 0 is the object surface. ``add`` inserts at this number, and following surfaces move up. The inserted surface is ``Standard`` until ``values`` sets ``type``.
    :param values: Keys to write. The fields are the same as those of one surface returned by :meth:`get_lens_data`. Omit ``values`` to insert a default surface or to remove a surface. ``surface_number`` is read-only. ``type`` is a surface type name, such as ``EvenAspheric``. ``parameters`` maps column names such as ``Par1`` to a number, a string, or an object with ``value`` and ``solve``. ``header`` is read-only. ``type`` is applied before ``parameters``. ``radius_solve`` and the other cell solves set that cell's solve; ``Fixed`` clears it. Omit ``column`` on a surface pickup to use the same column. Setting ``is_stop`` to true makes that surface the stop. The object and image surfaces cannot be removed.
    :returns: The surfaces after the change.
    :rtype: dict[str, object]
    :raises ValueError: The action, number, or values cannot be applied.
    """

    return mcp_server.read(ctx, lambda session: session.set_lens_rows(action, number, values))
