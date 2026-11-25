"""Analyze results that are not their own window."""


import mcp.server.mcpserver

import zaymcp.server as mcp_server

__all__ = [
    'get_first_order',
]

@mcp_server.server.tool(
    description=(
        'Return effective focal length, entrance pupil diameter, F-numbers, and total length for the open lens. '
        'Lengths are in lens units.'
    ),
)
def get_first_order(ctx: mcp.server.mcpserver.Context) -> dict[str, float | str | None]:
    """
    Return first-order values for the lens open in the OpticStudio window.

    The system is updated before the values are read. ``working_f_number`` is on axis at the primary wavelength. A number is ``None`` when OpticStudio does not return a finite value.

    :returns:
        * **effective_focal_length** -- Effective focal length, in lens units.
        * **entrance_pupil_diameter** -- Entrance pupil diameter, in lens units.
        * **image_space_f_number** -- Paraxial image-space F-number.
        * **working_f_number** -- Working F-number on axis at the primary wavelength.
        * **total_length** -- Thickness from surface 1 to the image surface, in lens units.
        * **status** -- Text reported while updating the system. Empty when the update reports nothing.
    :rtype: dict[str, float | str | None]
    """

    return mcp_server.read(ctx, lambda session: session.first_order())
