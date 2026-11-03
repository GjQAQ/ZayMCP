"""Stdio MCP server."""

import contextlib

import mcp.server
import mcp.server.mcpserver
import mcp.server.mcpserver.exceptions

import zemaxmcp.zosapi.session

__all__ = [
    'SERVER_NAME',
    'main',
    'read',
    'server',
]

#: Name announced to an MCP host.
SERVER_NAME: str = "ZemaxMCP"


class OpticStudioConnection:
    """Keep one Interactive Extension session for this server process."""

    def __init__(self) -> None:
        #: The shared OpticStudio session. ``None`` before the first tool call and after a failed call.
        self.session: zemaxmcp.zosapi.session.OpticStudioSession | None = None

    def open(self) -> zemaxmcp.zosapi.session.OpticStudioSession:
        """
        Return the shared session, connecting on first use.

        :returns: The Interactive Extension session.
        :rtype: zemaxmcp.zosapi.session.OpticStudioSession
        :raises zemaxmcp.zosapi.session.OpticStudioError: OpticStudio cannot be connected.
        """

        if self.session is None:
            self.session = zemaxmcp.zosapi.session.OpticStudioSession()

        return self.session

    def close(self) -> None:
        """Disconnect the shared session.

        Calling this again does nothing.
        """

        session = self.session
        self.session = None

        if session is not None:
            session.close()


@contextlib.asynccontextmanager
async def lifespan(server: mcp.server.MCPServer):
    """
    Keep one OpticStudio connection for the life of this server process.

    :param mcp.server.MCPServer server: The server being started.
    :returns: The connection yielded to each request.
    """

    # Close the OpticStudio connection when the host stops this process.
    connection = OpticStudioConnection()

    try:
        yield connection
    finally:
        connection.close()


server = mcp.server.MCPServer(SERVER_NAME, lifespan=lifespan)


def read(ctx, load):
    """
    Run one read against the shared session.

    The session is dropped when OpticStudio cannot answer, so the next call can reconnect.

    :param ctx: Tool context for this request.
    :param load: Called with the open session.
    :returns: The value returned by ``load``.
    :raises mcp.server.mcpserver.exceptions.ToolError: OpticStudio cannot answer.
    """

    # Drop the shared session when OpticStudio cannot answer, so the next call can reconnect.
    connection = ctx.request_context.lifespan_context

    try:
        return load(connection.open())
    except zemaxmcp.zosapi.session.OpticStudioError as exc:
        connection.close()
        raise mcp.server.mcpserver.exceptions.ToolError(str(exc)) from exc

@server.tool(
    description='Return version, license, and connection details for the OpticStudio window.',
)
def get_opticstudio_version(ctx: mcp.server.mcpserver.Context) -> dict[str, str | int]:
    """
    Return version details for the OpticStudio window waiting on Interactive Extension.

    :returns:
        * **product_name** -- Product name from ``OpticStudio.exe``.
        * **product_version** -- Product version, such as ``24.2.00.0``. The first two parts identify the release, so 24.2 is 2024 R2.
        * **file_version** -- File version of ``OpticStudio.exe``.
        * **file_description** -- File description of ``OpticStudio.exe``.
        * **opticstudio_version** -- Integer version reported by ZOS-API.
        * **zos_major_version** -- ZOS-API major version.
        * **zos_minor_version** -- ZOS-API minor version.
        * **zos_service_pack** -- ZOS-API service pack number. 0 means no service pack.
        * **license_status** -- License type, such as ``PremiumEdition``.
        * **mode** -- Connection mode. Interactive Extension reports ``Plugin``.
        * **installation_directory** -- Directory that contains ``OpticStudio.exe``.
        * **supported_release** -- Release this server supports. This value is fixed by the server.
    :rtype: dict[str, str | int]
    """

    return read(ctx, lambda session: session.version())

def main() -> None:
    """Serve MCP over stdio until the host closes the connection."""

    server.run()


# Importing a tool module registers its tools on server.
import zemaxmcp.tools.file.lens.save
import zemaxmcp.tools.setup.system.explorer
import zemaxmcp.tools.setup.editors.lens_data
import zemaxmcp.tools.setup.editors.multi_configuration
import zemaxmcp.tools.optimize.automatic_optimization.merit_function
import zemaxmcp.tools.optimize.automatic_optimization.optimization_wizard
import zemaxmcp.tools.analyze.image_quality.rays_and_spots.single_ray_trace
import zemaxmcp.tools.analyze.others
