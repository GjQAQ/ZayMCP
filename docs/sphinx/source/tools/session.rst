Session
=======

``get_opticstudio_version`` reads the OpticStudio window attached to this process.
``main`` serves MCP on stdio until the host disconnects.
``read`` runs one tool body on the shared connection and closes that connection when OpticStudio cannot answer.

The module-level ``server`` object is the MCP server that the tool modules decorate.

.. automodule:: zaymcp.server
   :members:
   :exclude-members: server
