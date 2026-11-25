ZayMCP
======

ZayMCP is a Python MCP server for Ansys Zemax OpticStudio 2024 R2.
These pages document the ``zaymcp`` package.

The package has two trees.

``zaymcp.tools`` holds the functions a host calls.
The path follows the OpticStudio ribbon, and the leaf module is the window, dialog, or analysis that function drives.
A tool function's docstring is the contract for its arguments and return fields.

``zaymcp.zosapi`` performs the ZOS-API calls for the matching tool path.
:class:`zaymcp.zosapi.session.OpticStudioSession` keeps one Interactive Extension connection and runs every call on a single STA thread.

The ``zaymcp`` command calls :func:`zaymcp.server.main`.
Importing :mod:`zaymcp.server` registers every tool on the process-wide server.
Each tool uses :func:`zaymcp.server.read` to run against that connection.

ZayMCP is an independent project.
It is not developed, maintained, endorsed, or affiliated with Ansys or Zemax.

.. toctree::
   :maxdepth: 2
   :caption: Tools

   tools/session
   tools/file
   tools/setup
   tools/optimize
   tools/analyze

.. toctree::
   :maxdepth: 2
   :caption: ZOS-API

   zosapi/connection
   zosapi/model
   zosapi/editors
   zosapi/optimization
