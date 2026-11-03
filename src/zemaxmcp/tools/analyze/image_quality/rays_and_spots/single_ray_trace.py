"""Single Ray Trace tool."""

import typing

import mcp.server.mcpserver

import zemaxmcp.server as mcp_server

__all__ = [
    'get_single_ray_trace',
]

@mcp_server.server.tool(
    description=(
        'Return the Single Ray Trace table for one ray. '
        '`hx` and `hy` are the normalized field coordinates. '
        '`px` and `py` are the normalized pupil coordinates. '
        '`trace_type` is `DirectionCosines`, `TangentAngle`, or `YmUmYcUc`.'
    ),
)
def get_single_ray_trace(
    ctx: mcp.server.mcpserver.Context,
    wavelength: int = 1,
    hx: float = 0,
    hy: float = 0,
    px: float = 0,
    py: float = 0,
    trace_type: typing.Literal['DirectionCosines', 'TangentAngle', 'YmUmYcUc'] = 'DirectionCosines',
) -> dict[str, object]:
    """
    Return the Single Ray Trace table for one ray in the open lens.

    ``hx`` and ``hy`` are the normalized field coordinates. ``px`` and ``py`` are the normalized pupil coordinates. ``trace_type`` selects Direction Cosines, Tangential Angle, or ``Ym, Um, Yc, Uc``.

    :param wavelength: 1-based wavelength number.
    :param hx: Normalized field coordinate X.
    :param hy: Normalized field coordinate Y.
    :param px: Normalized pupil coordinate X.
    :param py: Normalized pupil coordinate Y.
    :param trace_type: ``DirectionCosines``, ``TangentAngle``, or ``YmUmYcUc``.
    :returns:
        * **wavelength** -- Wavelength number used for the ray.
        * **hx** -- Normalized field coordinate X.
        * **hy** -- Normalized field coordinate Y.
        * **px** -- Normalized pupil coordinate X.
        * **py** -- Normalized pupil coordinate Y.
        * **type** -- Table format.
        * **columns** -- Headings of the Single Ray Trace table, after the surface column.
        * **surfaces** -- One entry per surface, in the order shown in the window.
        * **surfaces[].surface** -- Surface label from the table, such as ``OBJ``, a surface number, or ``IMA``.
        * **surfaces[].values** -- One number per heading. ``None`` where the table has no finite number.
        * **message** -- Error line under the table. Empty when the table has none.
    :rtype: dict[str, object]
    :raises ValueError: The ray settings or the table cannot be used.
    """

    return mcp_server.read(
        ctx,
        lambda session: session.single_ray_trace(wavelength, hx, hy, px, py, trace_type),
    )
