"""Create a new lens and return its identity."""

import mcp.server.mcpserver

import zaymcp.server as mcp_server

__all__ = [
    'new_lens',
]


@mcp_server.server.tool(
    description=(
        'Replace the open lens with a new lens. '
        'Unsaved changes are discarded only when `discard_changes` is true.'
    ),
)
def new_lens(
    ctx: mcp.server.mcpserver.Context,
    discard_changes: bool = False,
) -> dict[str, str | bool]:
    """
    Replace the lens open in the OpticStudio window with a new lens and return its identity.

    A lens with unsaved changes stays open unless ``discard_changes`` is true. The new lens has not been saved.

    :param discard_changes: True discards unsaved changes. False refuses when the open lens needs to be saved.
    :returns: The lens identity after the new lens is created. The fields are the same as those returned by :meth:`get_lens_metadata`.
    :rtype: dict[str, str | bool]
    :raises ValueError: The lens has unsaved changes and ``discard_changes`` is false, or OpticStudio cannot create the lens.
    """

    return mcp_server.read(ctx, lambda session: session.new_lens(discard_changes))
