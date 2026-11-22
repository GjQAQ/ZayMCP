Editors
=======

Each editor object reads a ZOS-API editor into dictionaries and writes those dictionaries back.
:class:`~zaymcp.zosapi.session.OpticStudioSession` calls these objects from its public methods.

:data:`~zaymcp.zosapi.setup.system.explorer.SYSTEM`, :data:`~zaymcp.zosapi.setup.editors.lens_data.LENS`, and :data:`~zaymcp.zosapi.setup.editors.multi_configuration.MULTI` are the column lists those methods use.
The pages include their descriptions and omit the ZOS-API object values.

System Explorer
---------------

.. automodule:: zaymcp.zosapi.setup.system.explorer
   :members:
   :exclude-members: SYSTEM

.. autodata:: zaymcp.zosapi.setup.system.explorer.SYSTEM
   :no-value:

Lens Data Editor
----------------

.. automodule:: zaymcp.zosapi.setup.editors.lens_data
   :members:
   :exclude-members: LENS

.. autodata:: zaymcp.zosapi.setup.editors.lens_data.LENS
   :no-value:

Multi-Configuration Editor
--------------------------

.. automodule:: zaymcp.zosapi.setup.editors.multi_configuration
   :members:
   :exclude-members: MULTI

.. autodata:: zaymcp.zosapi.setup.editors.multi_configuration.MULTI
   :no-value:
