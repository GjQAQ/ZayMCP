"""A connection to one open OpticStudio window.

ZOS-API calls run on a single STA thread. The user opens Interactive
Extension first. An instance number of 0 attaches to whichever window is
waiting. The installation is located through Zemax's own helper. When that
cannot find OpticStudio, set OPTICSTUDIO_DIRECTORY to the installation
directory.
"""

import ctypes
import os
import queue
import threading
import winreg

from zaymcp.zosapi.analyze.image_quality.rays_and_spots.single_ray_trace import _single_ray_trace
from zaymcp.zosapi.analyze.others import _read_first_order
from zaymcp.zosapi.errors import OpticStudioError
from zaymcp.zosapi.file.lens.new import _new_lens
from zaymcp.zosapi.file.lens.save import _save_lens
from zaymcp.zosapi.model.fields import text
from zaymcp.zosapi.optimize.automatic_optimization.merit_function import MERIT, _calculate_merit
from zaymcp.zosapi.optimize.automatic_optimization.optimization_wizard import _apply_optimization_wizard
from zaymcp.zosapi.setup.editors.lens_data import LENS
from zaymcp.zosapi.setup.editors.multi_configuration import MULTI
from zaymcp.zosapi.setup.system.explorer import row_editor, setting_group

__all__ = [
    'OpticStudioError',
    'OpticStudioSession',
    'SUPPORTED_RELEASE',
]

#: COM apartment of the thread that owns the ZOS-API objects. 2 is an STA.
COINIT_APARTMENTTHREADED: int = 2

#: OpticStudio release this server supports.
SUPPORTED_RELEASE: str = "2024 R2"


class OpticStudioSession:
    """
    Own one Interactive Extension connection and the thread that calls it.

    :param int instance: OpticStudio instance number. ``0`` attaches to whichever window is waiting.
    :param str directory: Installation directory. When omitted, Zemax's helper locates it, then ``OPTICSTUDIO_DIRECTORY`` is used.
    :raises OpticStudioError: OpticStudio cannot be located, or the connection fails.
    """

    #: OpticStudio installation directory this session is connected to.
    installation_directory: str

    def __init__(self, instance: int = 0, directory: str | None = None):
        #: OpticStudio instance number. ``0`` attaches to whichever window is waiting.
        self.instance: int = instance
        #: Installation directory passed to this session.
        #: ``None`` means Zemax's helper locates OpticStudio, then ``OPTICSTUDIO_DIRECTORY`` is used.
        self.directory: str | None = directory
        # The queue, thread, and ZOS-API objects are usable only on this session's thread.
        self._jobs = queue.Queue()
        self._ready = threading.Event()
        self._startup_error = None
        self._closed = False
        self._application = None
        self._system = None
        self._thread = threading.Thread(target=self._run, name="zos-api")

        self._thread.start()
        self._ready.wait()

        if self._startup_error is not None:
            self._closed = True
            self._thread.join()
            raise self._startup_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

        # False means an exception from the with-block still propagates.
        return False

    def close(self):
        """
        Disconnect from Interactive Extension and stop the ZOS-API thread.

        Calling this again does nothing.
        """

        if self._closed:
            return

        self._closed = True
        self._jobs.put(None)
        self._thread.join()

    def system_file(self):
        """
        Return the file path of the lens open in the OpticStudio window.

        :returns: The lens file path. An unsaved system returns an empty string.
        :rtype: str
        :raises OpticStudioError: The session is already closed.
        """

        # SystemFile is the path of the lens open in the OpticStudio window.
        return self.call(lambda: str(self._system.SystemFile))

    def lens_file(self) -> dict[str, str | bool]:
        """
        Return identity details for the lens open in the OpticStudio window.

        :returns: The file path and name, title, author, and notes, the sequential or non-sequential mode, and whether the file has unsaved changes.
        :rtype: dict[str, str | bool]
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(self._read_lens_file)

    def version(self) -> dict[str, str | int]:
        """
        Return version details for the connected OpticStudio.

        :returns: Product, file, and ZOS-API version fields, plus the license and connection mode of this window.
        :rtype: dict[str, str | int]
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(self._read_version)

    def system_data(self, name: str) -> dict[str, object] | list[dict[str, object]]:
        """
        Return one System Explorer section for the lens open in the OpticStudio window.

        :param str name: ``units``, ``aperture``, ``fields``, ``wavelengths``, ``environment``, ``polarization``, or ``ray_aiming``.
        :returns: The group values. Wavelengths are a list. The other groups are dictionaries.
        :rtype: dict[str, object] | list[dict[str, object]]
        :raises ValueError: ``name`` is not a setting group.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        section = setting_group(name)

        return self.call(lambda: section.read(self._system.SystemData))

    def set_system_data(self, name: str, values: dict[str, object]) -> dict[str, object] | list[dict[str, object]]:
        """
        Change keys in one System Explorer setting group and return the group.

        Only keys in ``values`` are written. Field points and the wavelength list are rows and stay unchanged.

        :param str name: Setting group. The same names as :meth:`system_data`.
        :param dict[str, object] values: Keys to change. The fields are the same as those returned by :meth:`system_data` for that group.
        :returns: The setting group after the change.
        :rtype: dict[str, object] | list[dict[str, object]]
        :raises ValueError: ``name`` is unknown, ``values`` is empty, or a key cannot be changed.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        if not values:
            raise ValueError('values must contain the keys to change.')

        section = setting_group(name)

        def change():
            section.write(self._system.SystemData, values)

            return section.read(self._system.SystemData)

        return self.call(change)

    def set_system_rows(
        self,
        name: str,
        action: str,
        number: int | None,
        values: dict[str, object] | None,
    ) -> list[dict[str, object]]:
        """
        Change, add, or remove one field point or wavelength, then return the rows.

        ``add`` appends a row. ``make_primary`` selects the primary wavelength.

        :param str name: ``fields`` or ``wavelengths``.
        :param str action: ``change``, ``add``, ``remove``, or ``make_primary``.
        :param int | None number: 1-based row. Required for ``change``, ``remove``, and ``make_primary``.
        :param dict[str, object] | None values: Keys to write. The fields are the same as those of one row returned by :meth:`system_data`.
        :returns: The rows after the change. Field rows are the field points.
        :rtype: list[dict[str, object]]
        :raises ValueError: ``name`` has no row list, or the action, number, or values cannot be applied.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        source, rows = row_editor(name)

        def change():
            data = getattr(self._system.SystemData, source)
            rows.edit(data, action, number, values)

            return rows.read(data)

        return self.call(change)

    def lens_data(self, surface: int | None = None) -> dict[str, object]:
        """
        Return Lens Data Editor surfaces for the lens open in the OpticStudio window.

        :param int | None surface: One surface number. ``None`` reads every surface. 0 is the object surface.
        :returns: Every surface, or the one requested surface. Each surface includes the parameter columns its type uses.
        :rtype: dict[str, object]
        :raises ValueError: ``surface`` is outside the editor.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(lambda: LENS.read(self._system.LDE, surface))

    def set_lens_rows(
        self,
        action: str,
        number: int | None,
        values: dict[str, object] | None,
    ) -> dict[str, object]:
        """
        Change, insert, or remove one Lens Data Editor surface and return the editor.

        ``add`` inserts a surface at ``number``. Surfaces at that number and after move up.

        :param str action: ``change``, ``add``, or ``remove``.
        :param int | None number: Surface number. 0 is the object surface.
        :param dict[str, object] | None values: Keys to write. The fields are the same as those of one surface returned by :meth:`lens_data`. ``type`` changes the surface type first. ``parameters`` maps column names such as ``Par1`` to a value or to ``value`` and ``solve``. ``radius_solve`` and the other cell solves set that cell's solve.
        :returns: The surfaces after the change.
        :rtype: dict[str, object]
        :raises ValueError: The action, number, or values cannot be applied.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        def change():
            editor = self._system.LDE
            LENS.edit(editor, action, number, values)

            return LENS.read(editor)

        return self.call(change)

    def merit_function(self, operand: int | None = None) -> dict[str, object]:
        """
        Return Merit Function Editor operands for the lens open in the OpticStudio window.

        :param int | None operand: One 1-based operand number. ``None`` reads every operand.
        :returns: Every operand, or the one requested operand. Each operand includes the parameter columns its type uses.
        :rtype: dict[str, object]
        :raises ValueError: ``operand`` is outside the editor.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(lambda: MERIT.read(self._system.MFE, operand))

    def set_merit_rows(
        self,
        action: str,
        number: int | None,
        values: dict[str, object] | None,
    ) -> dict[str, object]:
        """
        Change, insert, or remove one Merit Function Editor operand and return the editor.

        ``add`` inserts an operand at ``number``. Operands at that number and after move up.

        :param str action: ``change``, ``add``, or ``remove``.
        :param int | None number: 1-based operand number.
        :param dict[str, object] | None values: Keys to write. The fields are the same as those of one operand returned by :meth:`merit_function`. ``type`` changes the operand type first. ``parameters`` maps column names such as ``Param1`` to new values.
        :returns: The operands after the change.
        :rtype: dict[str, object]
        :raises ValueError: The action, number, or values cannot be applied.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        def change():
            editor = self._system.MFE
            MERIT.edit(editor, action, number, values)

            return MERIT.read(editor)

        return self.call(change)

    def multi_configuration(self, operand: int | None = None) -> dict[str, object]:
        """
        Return the Multi-Configuration Editor for the lens open in the OpticStudio window.

        :param int | None operand: One 1-based operand number. ``None`` reads every operand.
        :returns: The current configuration, the configuration columns, and the operands. With ``operand``, that operand.
        :rtype: dict[str, object]
        :raises ValueError: ``operand`` is outside the editor.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(lambda: MULTI.read(self._system.MCE, operand))

    def set_multi_configuration_rows(
        self,
        section: str,
        action: str,
        number: int | None,
        values: dict[str, object] | None,
    ) -> dict[str, object]:
        """
        Change one Multi-Configuration Editor operand or configuration and return the editor.

        ``add`` inserts at ``number``. Following operands or configurations move up.

        :param str section: ``operand`` or ``configuration``.
        :param str action: ``change``, ``add``, ``remove``, or ``make_current``.
        :param int | None number: 1-based operand or configuration number.
        :param dict[str, object] | None values: Keys to write. For an operand, the fields are the same as those of one operand returned by :meth:`multi_configuration`. ``type`` changes the operand type first. ``parameters`` maps ``Param1``, ``Param2``, or ``Param3`` to an integer. ``cells`` maps a configuration number to a value or to ``value`` and ``solve``. For a new configuration, ``copy`` copies the current configuration's cells.
        :returns: The editor after the change.
        :rtype: dict[str, object]
        :raises ValueError: The section, action, number, or values cannot be applied.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        def change():
            editor = self._system.MCE
            MULTI.edit(editor, section, action, number, values)

            return MULTI.read(editor)

        return self.call(change)

    def apply_optimization_wizard(self, values: dict[str, object] | None = None) -> dict[str, object]:
        """
        Apply the Optimization Wizard and return the settings and operands.

        The wizard is reset to its dialog defaults. Keys in ``values`` then replace those defaults. Omit ``values`` to keep every default. Operands from the wizard's Start At row through the end of the editor are replaced. ``value`` and ``contribution`` are whatever the editor shows after that, and are not calculated.

        :param dict[str, object] | None values: Wizard controls to change. The fields are the same as ``settings`` in the result. A glass or air thickness turns that boundary on when its checkbox is omitted. ``configuration`` selects one configuration, and ``field`` selects one field, when the matching "all" checkbox is omitted.
        :returns: ``settings`` and ``operands``. ``settings`` are the wizard controls that were applied. Each operand has the same fields as :meth:`merit_function`.
        :rtype: dict[str, object]
        :raises ValueError: A wizard setting cannot be applied.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(lambda: _apply_optimization_wizard(self._system.MFE, values))

    def calculate_merit_function(self) -> dict[str, object]:
        """
        Calculate the merit function and return its value and the operands.

        ``value`` and ``contribution`` on each operand are the numbers from this calculation.

        :returns: ``merit`` and ``operands``. ``merit`` is ``None`` when OpticStudio does not return a finite value. Each operand has the same fields as :meth:`merit_function`.
        :rtype: dict[str, object]
        :raises ValueError: The merit function cannot be calculated.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(lambda: _calculate_merit(self._system.MFE))

    def single_ray_trace(
        self,
        wavelength: int = 1,
        hx: float = 0,
        hy: float = 0,
        px: float = 0,
        py: float = 0,
        trace_type: str = 'DirectionCosines',
    ) -> dict[str, object]:
        """
        Return the Single Ray Trace table for one ray.

        ``hx`` and ``hy`` are the normalized field coordinates. ``px`` and ``py`` are the normalized pupil coordinates. ``trace_type`` selects the table shown in that window.

        :param int wavelength: 1-based wavelength number.
        :param float hx: Normalized field coordinate X.
        :param float hy: Normalized field coordinate Y.
        :param float px: Normalized pupil coordinate X.
        :param float py: Normalized pupil coordinate Y.
        :param str trace_type: ``DirectionCosines``, ``TangentAngle``, or ``YmUmYcUc``.
        :returns: The ray settings and one row per surface. ``columns`` are the table headings. ``values`` follow those headings. A missing number, such as an infinite object thickness, is ``None``. ``message`` is empty when the table has no error line.
        :rtype: dict[str, object]
        :raises ValueError: The ray settings or the table cannot be used.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(lambda: _single_ray_trace(self._system, wavelength, hx, hy, px, py, trace_type))

    def first_order(self) -> dict[str, float | str | None]:
        """
        Return first-order values for the lens open in the OpticStudio window.

        The system is updated first. Lengths are in lens units. ``working_f_number`` is the on-axis value at the primary wavelength. ``total_length`` runs from surface 1 to the image surface.

        :returns: Effective focal length, entrance pupil diameter, paraxial and working F-numbers, and total length. A number is ``None`` when OpticStudio does not return a finite value. ``status`` is empty when the update reports nothing.
        :rtype: dict[str, float | str | None]
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(lambda: _read_first_order(self._system))

    def new_lens(self, discard_changes: bool = False) -> dict[str, str | bool]:
        """
        Replace the lens open in the OpticStudio window with a new lens.

        Unsaved changes are discarded only when ``discard_changes`` is true. A lens with unsaved changes is left open otherwise. The new lens has not been saved.

        :param bool discard_changes: True discards unsaved changes. False refuses when the lens needs to be saved.
        :returns: The lens identity after the new lens is created. The fields are the same as those returned by :meth:`lens_file`.
        :rtype: dict[str, str | bool]
        :raises ValueError: The lens has unsaved changes and ``discard_changes`` is false, or OpticStudio cannot create the lens.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        def write():
            _new_lens(self._system, discard_changes)

            return self._read_lens_file()

        return self.call(write)

    def save(self, path: str | None = None) -> dict[str, str | bool]:
        """
        Save the lens open in the OpticStudio window.

        Omit ``path`` to save the current file. Pass a full path to save the lens as a new file. An existing file at that path is replaced. A lens that has never been saved needs a path.

        :param str | None path: Full path of the new lens file. ``None`` saves the current file.
        :returns: The lens identity after the save. The fields are the same as those returned by :meth:`lens_file`.
        :rtype: dict[str, str | bool]
        :raises ValueError: The lens has no current file, ``path`` is not a full path, or OpticStudio cannot save.
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        def write():
            _save_lens(self._system, path)

            return self._read_lens_file()

        return self.call(write)

    def call(self, function):
        """
        Run a function on the ZOS-API thread and return its result.

        An exception raised by ``function`` propagates to the caller.

        :param function: Called on the session thread.
        :returns: The value returned by ``function``.
        :raises OpticStudioError: The session is already closed.
        """

        # Hand function to the ZOS-API thread and wait for its result.
        if self._closed:
            raise OpticStudioError("The OpticStudio session is closed.")

        done = queue.Queue(maxsize=1)
        self._jobs.put((function, done))
        ok, value = done.get()

        if not ok:
            raise value

        return value

    def _run(self):
        # Body of the ZOS-API thread: connect, then run queued calls until close.
        try:
            _initialize_sta()
            self._connect()
        except Exception as exc:
            self._startup_error = exc
            self._close_application()
            self._ready.set()

            return

        self._ready.set()

        try:
            while True:
                item = self._jobs.get()

                if item is None:
                    break

                function, done = item

                try:
                    done.put((True, function()))
                except Exception as exc:
                    done.put((False, exc))
        finally:
            self._close_application()
            ctypes.windll.ole32.CoUninitialize()

    def _connect(self):
        import pythonnet

        # ZOS-API is built on .NET Framework, so pythonnet must load that runtime.
        pythonnet.load("netfx")

        import clr

        # NetHelper locates the OpticStudio installation. It ships in the Zemax data folder.
        clr.AddReference(net_helper_path())

        directory = locate_opticstudio(self.directory)
        require_supported_release(directory)
        self.installation_directory = directory

        # These two assemblies are the ZOS-API itself, loaded from that installation.
        clr.AddReference(os.path.join(directory, "ZOSAPI.dll"))
        clr.AddReference(os.path.join(directory, "ZOSAPI_Interfaces.dll"))

        import ZOSAPI

        connection = ZOSAPI.ZOSAPI_Connection()

        if connection is None:
            raise OpticStudioError("Unable to initialize the ZOS-API connection.")

        # Attach to the Interactive Extension dialog the user already opened.
        # Instance 0 means whichever waiting window is available.
        application = connection.ConnectAsExtension(self.instance)

        if application is None:
            raise OpticStudioError("Unable to acquire the OpticStudio application.")

        # The open seat must include a license that allows ZOS-API use.
        if not application.IsValidLicenseForAPI:
            application.CloseApplication()
            raise OpticStudioError("The license is not valid for the ZOS-API.")

        # PrimarySystem is the lens currently displayed in that window.
        system = application.PrimarySystem

        if system is None:
            application.CloseApplication()
            raise OpticStudioError("Unable to acquire the primary system.")

        self._application = application
        self._system = system

    def _read_version(self) -> dict[str, str | int]:
        # Read on the ZOS-API thread. File versions come from OpticStudio.exe; the rest come from the open application.
        import System.Diagnostics

        executable = os.path.join(self.installation_directory, "OpticStudio.exe")
        info = System.Diagnostics.FileVersionInfo.GetVersionInfo(executable)
        application = self._application

        return {
            "product_name": text(info.ProductName),
            "product_version": text(info.ProductVersion),
            "file_version": text(info.FileVersion),
            "file_description": text(info.FileDescription),
            "opticstudio_version": int(application.OpticStudioVersion),
            "zos_major_version": int(application.ZOSMajorVersion),
            "zos_minor_version": int(application.ZOSMinorVersion),
            "zos_service_pack": int(application.ZOSSPVersion),
            "license_status": str(application.LicenseStatus),
            "mode": str(application.Mode),
            "installation_directory": self.installation_directory,
            "supported_release": SUPPORTED_RELEASE,
        }

    def _read_lens_file(self) -> dict[str, str | bool]:
        # Read on the ZOS-API thread. Title, author, and notes are the System Explorer Title/Notes fields.
        system = self._system
        title_notes = system.SystemData.TitleNotes

        return {
            "file": text(system.SystemFile),
            "name": text(system.SystemName),
            "title": text(title_notes.Title),
            "author": text(title_notes.Author),
            "notes": text(title_notes.Notes),
            "mode": str(system.Mode),
            "needs_save": bool(system.NeedsSave),
            "is_project_directory": bool(system.IsProjectDirectory),
        }

    def _close_application(self):
        application = self._application
        self._application = None
        self._system = None

        if application is not None:
            # For an Interactive Extension this ends the external connection.
            application.CloseApplication()


def _initialize_sta():
    # Mark this thread as the COM apartment that will own the ZOS-API objects.
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    ole32.CoInitializeEx.restype = ctypes.c_long
    result = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)

    if result < 0:
        raise OpticStudioError("The ZOS-API thread could not join an STA.")


def locate_opticstudio(directory: str | None) -> str:
    """
    Return the OpticStudio installation directory.

    Zemax's helper is asked first. When ``directory`` is omitted and that cannot find OpticStudio, ``OPTICSTUDIO_DIRECTORY`` is used.

    :param str | None directory: Installation directory. ``None`` asks Zemax's helper, then the environment variable.
    :returns: The installation directory.
    :rtype: str
    :raises OpticStudioError: OpticStudio cannot be located.
    """

    import ZOSAPI_NetHelper

    # Initialize() asks NetHelper where OpticStudio is installed.
    initializer = ZOSAPI_NetHelper.ZOSAPI_Initializer

    if directory:
        if not initializer.Initialize(directory):
            raise OpticStudioError(f"Unable to initialize OpticStudio at {directory}.")
    elif not initializer.Initialize():
        directory = os.environ.get("OPTICSTUDIO_DIRECTORY")

        if not directory:
            raise OpticStudioError(
                "Unable to locate OpticStudio. Set OPTICSTUDIO_DIRECTORY to the installation directory."
            )

        if not initializer.Initialize(directory):
            raise OpticStudioError(f"Unable to initialize OpticStudio at {directory}.")

    return str(initializer.GetZemaxDirectory())


def require_supported_release(directory: str) -> None:
    """
    Reject an OpticStudio installation that is not the supported release.

    :param str directory: Installation directory that contains ``OpticStudio.exe``.
    :raises OpticStudioError: The product version is not 2024 R2.
    """

    import System.Diagnostics

    executable = os.path.join(directory, "OpticStudio.exe")
    info = System.Diagnostics.FileVersionInfo.GetVersionInfo(executable)
    numbers = str(info.ProductVersion).split(".")

    if numbers[:2] != ["24", "2"]:
        raise OpticStudioError(
            f"OpticStudio {SUPPORTED_RELEASE} is the supported release. Found {info.ProductVersion}."
        )


def net_helper_path() -> str:
    """
    Return the path of ``ZOSAPI_NetHelper.dll`` in the Zemax data folder.

    :returns: The helper assembly path.
    :rtype: str
    :raises OSError: The Zemax registry key or ``ZemaxRoot`` value is missing.
    """

    # ZemaxRoot is the data folder OpticStudio created, not the program directory.
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Zemax")

    try:
        root, _value_type = winreg.QueryValueEx(key, "ZemaxRoot")
    finally:
        winreg.CloseKey(key)

    # "ZemaxData" folder under installation directory of zemax
    return os.path.join(root, "ZOS-API", "Libraries", "ZOSAPI_NetHelper.dll")
