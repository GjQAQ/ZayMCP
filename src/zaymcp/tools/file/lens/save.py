"""Save the open lens and return its identity."""


import mcp.server.mcpserver

import zaymcp.server as mcp_server

__all__ = [
    'get_lens_metadata',
    'save_lens',
]

@mcp_server.server.tool(
    description='Return the identity of the lens, including whether it has unsaved changes.',
)
def get_lens_metadata(ctx: mcp.server.mcpserver.Context) -> dict[str, str | bool]:
    """
    Return identity details for the lens open in the OpticStudio window.

    :returns:
        * **file** -- Full path of the lens file. Empty when the lens has not been saved.
        * **name** -- System name.
        * **title** -- Lens title from System Explorer Title/Notes.
        * **author** -- Author from System Explorer Title/Notes.
        * **notes** -- Notes from System Explorer Title/Notes.
        * **mode** -- ``Sequential`` or ``NonSequential``.
        * **needs_save** -- True when the window has unsaved changes.
        * **is_project_directory** -- True when the lens is stored as a project directory rather than a single file.
    :rtype: dict[str, str | bool]
    """

    return mcp_server.read(ctx, lambda session: session.lens_file())


@mcp_server.server.tool(
    description=(
        'Save the open lens. Omit `path` to save the current file. '
        'Pass a full `path` to save it as a new file. '
        'An existing file at that path is replaced.'
    ),
)
def save_lens(
    ctx: mcp.server.mcpserver.Context,
    path: str | None = None,
) -> dict[str, str | bool]:
    """
    Save the lens open in the OpticStudio window and return its identity.

    Omit ``path`` to save the current file. Pass a full path to save the lens as a new file. The window then uses that file. An existing file at that path is replaced. A lens that has never been saved needs a path.

    :param path: Full path of the new lens file, such as a ``.zmx`` or ``.zos`` file. ``None`` saves the current file.
    :returns: The lens identity after the save. The fields are the same as those returned by :meth:`get_lens_metadata`.
    :rtype: dict[str, str | bool]
    :raises ValueError: The lens has no current file, ``path`` is not a full path, or OpticStudio cannot save.
    """

    return mcp_server.read(ctx, lambda session: session.save(path))
