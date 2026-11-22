Connection
==========

:class:`~zaymcp.zosapi.session.OpticStudioSession` owns the Interactive Extension connection for this process.
Creating a session starts the STA thread and connects to the OpticStudio window that is waiting.
The session methods are the operations the tools call.
Close the session with :meth:`~zaymcp.zosapi.session.OpticStudioSession.close`, or use it as a context manager.

:data:`~zaymcp.zosapi.session.SUPPORTED_RELEASE` is the release this server accepts.
:exc:`~zaymcp.zosapi.errors.OpticStudioError` is raised when OpticStudio cannot be located or cannot answer.

.. automodule:: zaymcp.zosapi.session
   :members:
   :exclude-members: OpticStudioError

.. automodule:: zaymcp.zosapi.errors
   :members:
   :show-inheritance:
