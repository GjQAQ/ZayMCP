"""A connection to one open OpticStudio window.

ZOS-API calls run on a single STA thread. The user opens Interactive
Extension first. An instance number of 0 attaches to whichever window is
waiting. The installation is located through Zemax's own helper. When that
cannot find OpticStudio, set OPTICSTUDIO_DIRECTORY to the installation
directory.
"""

import collections.abc
import ctypes
import dataclasses
import os
import queue
import threading
import winreg

# ZOS-API is a COM object and must be called from the thread that created it.
#: COM apartment of the thread that owns the ZOS-API objects. 2 is an STA.
COINIT_APARTMENTTHREADED: int = 2

#: OpticStudio release this server supports.
SUPPORTED_RELEASE: str = "2024 R2"

__all__ = [
    "OpticStudioError",
    "OpticStudioSession",
    "SUPPORTED_RELEASE",
]


class OpticStudioError(Exception):
    """OpticStudio could not be located or used."""


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
        :param dict[str, object] values: Keys to change. Names match the object returned for that group.
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


def text(value: object) -> str:
    """
    Return a ZOS-API string, using an empty string when the value is missing.

    :param object value: Value returned by ZOS-API. ``None`` is missing.
    :returns: The text, or an empty string when ``value`` is ``None``.
    :rtype: str
    """

    if value is None:
        return ""

    return str(value)


@dataclasses.dataclass(frozen=True)
class Attribute:
    """
    One ZOS-API member copied into a result field.

    :param str name: Key in the result.
    :param source: Property name, or a path of property names. The last member is called when ``call`` is true.
    :type source: str | tuple[str, ...]
    :param convert: Converts the raw value.
    :type convert: collections.abc.Callable[[object], object]
    :param bool call: When true, call the last member before converting it.
    :param bool writable: When true, ``set_system_settings`` may change this member.
    :param str | None enumeration: ZOS-API enumeration type in ``ZOSAPI.SystemData``. ``None`` when the member is not an enumeration.
    """

    #: Key in the result.
    name: str
    #: Property name, or a path of property names.
    source: str | tuple[str, ...]
    #: Converts the raw value.
    convert: collections.abc.Callable[[object], object]
    #: When true, call the last member before converting it.
    call: bool = False
    #: When true, ``set_system_settings`` may change this member.
    writable: bool = True
    #: ZOS-API enumeration type in ``ZOSAPI.SystemData``. ``None`` when the member is not an enumeration.
    enumeration: str | None = None

    def read(self, data) -> object:
        """
        Read this member from a ZOS-API object.

        :param data: Object that exposes ``source``.
        :returns: The converted value.
        :rtype: object
        """

        # Walk a property path, then optionally call the last member.
        parent, leaf = self._parent_and_leaf(data)
        raw = getattr(parent, leaf)

        if self.call:
            raw = raw()

        return self.convert(raw)

    def value_for_write(self, value: object) -> object:
        """
        Convert a tool value into the value stored by ZOS-API.

        :param object value: Value supplied for this member.
        :returns: The value to assign.
        :rtype: object
        :raises ValueError: ``value`` does not match this member.
        """

        if self.enumeration is not None:
            if not isinstance(value, str):
                raise ValueError(f'{self.name} must be a string.')

            return _enum_member(self.enumeration, self.name, value)

        if self.convert is bool:
            if not isinstance(value, bool):
                raise ValueError(f'{self.name} must be a boolean.')

            return value

        if self.convert is int:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'{self.name} must be an integer.')

            if isinstance(value, float) and not value.is_integer():
                raise ValueError(f'{self.name} must be an integer.')

            return int(value)

        if self.convert is float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'{self.name} must be a number.')

            return float(value)

        raise ValueError(f'{self.name} cannot be changed.')

    def assign(self, data, value: object) -> None:
        """
        Assign a tool value to this member.

        :param data: Object that exposes ``source``.
        :param object value: Value supplied for this member.
        :raises ValueError: ``value`` does not match this member.
        """

        self._place(data, self.value_for_write(value))

    @classmethod
    def record(cls, data, attributes: tuple['Attribute', ...]) -> dict[str, object]:
        """
        Copy attributes of one object into a dictionary.

        :param data: Object that exposes each attribute.
        :param tuple[Attribute, ...] attributes: Attributes to copy.
        :returns: Values keyed by attribute name.
        :rtype: dict[str, object]
        """

        return {item.name: item.read(data) for item in attributes}

    def _parent_and_leaf(self, data):
        # The last path entry is the member. Earlier entries are the objects that contain it.
        path = self.source if isinstance(self.source, tuple) else (self.source,)
        parent = data

        for name in path[:-1]:
            parent = getattr(parent, name)

        return parent, path[-1]

    def _place(self, data, value: object) -> None:
        # ``value`` is already converted. A getter such as GetFieldType is written through SetFieldType.
        parent, leaf = self._parent_and_leaf(data)

        if self.call:
            getattr(parent, 'Set' + leaf[3:])(value)

            return

        setattr(parent, leaf, value)


@dataclasses.dataclass(frozen=True)
class Rows:
    """
    A 1-based ZOS-API list copied into a list of dictionaries.

    :param str count: Property that holds the number of rows.
    :param str item: Method that returns one row. The argument is a 1-based index.
    :param attributes: Attributes copied from each row.
    :type attributes: tuple[Attribute, ...]
    """

    #: Property that holds the number of rows.
    count: str
    #: Method that returns one row. The argument is a 1-based index.
    item: str
    #: Attributes copied from each row.
    attributes: tuple[Attribute, ...]

    def read(self, data) -> list[dict[str, object]]:
        """
        Read every row.

        :param data: Object that exposes ``count`` and ``item``.
        :returns: One dictionary per row.
        :rtype: list[dict[str, object]]
        """

        # ZOS-API collections are 1-based.
        getter = getattr(data, self.item)
        total = int(getattr(data, self.count))
        rows = []

        for index in range(1, total + 1):
            rows.append(Attribute.record(getter(index), self.attributes))

        return rows


@dataclasses.dataclass(frozen=True)
class Section:
    """
    One SystemData child copied into a dictionary.

    :param str source: Property name on SystemData.
    :param attributes: Members read from that child.
    :type attributes: tuple[Attribute, ...]
    :param rows: Named collections read from that child.
    :type rows: tuple[tuple[str, Rows], ...]
    """

    #: Property name on SystemData.
    source: str
    #: Members read from that child.
    attributes: tuple[Attribute, ...] = ()
    #: Named collections read from that child. Each entry is a result key and the rows to read.
    rows: tuple[tuple[str, Rows], ...] = ()

    def read(self, system_data) -> dict[str, object]:
        """
        Read this section from system data.

        :param system_data: The ZOS-API ``SystemData`` object.
        :returns: Members and named collections.
        :rtype: dict[str, object]
        """

        data = getattr(system_data, self.source)
        result = Attribute.record(data, self.attributes)

        for name, rows in self.rows:
            result[name] = rows.read(data)

        return result

    def write(self, system_data, values: dict[str, object]) -> None:
        """
        Change selected members of this section.

        :param system_data: The ZOS-API ``SystemData`` object.
        :param dict[str, object] values: Keys to change. Names match :meth:`read`.
        :raises ValueError: A key is unknown, read-only, or names a list of rows.
        """

        by_name = {item.name: item for item in self.attributes}
        row_names = {name for name, _rows in self.rows}
        prepared = []

        for key, value in values.items():
            if key in row_names:
                raise ValueError(f'{key} is a list of rows and cannot be changed with set_system_settings.')

            attribute = by_name.get(key)

            if attribute is None:
                allowed = ', '.join(item.name for item in self.attributes if item.writable)
                raise ValueError(f'Unknown setting {key!r}. Expected one of: {allowed}.')

            if not attribute.writable:
                raise ValueError(f'{key} is read-only.')

            prepared.append((attribute, attribute.value_for_write(value)))

        data = getattr(system_data, self.source)

        for attribute, value in prepared:
            attribute._place(data, value)


@dataclasses.dataclass(frozen=True)
class Listing:
    """
    One SystemData child copied into a list of dictionaries.

    :param str source: Property name on SystemData.
    :param Rows rows: The 1-based collection on that child.
    """

    #: Property name on SystemData.
    source: str
    #: The 1-based collection on that child.
    rows: Rows

    def read(self, system_data) -> list[dict[str, object]]:
        """
        Read this listing from system data.

        :param system_data: The ZOS-API ``SystemData`` object.
        :returns: One dictionary per row.
        :rtype: list[dict[str, object]]
        """

        return self.rows.read(getattr(system_data, self.source))

    def write(self, system_data, values: dict[str, object]) -> None:
        """
        Reject a write to a list of rows.

        :param system_data: The ZOS-API ``SystemData`` object.
        :param dict[str, object] values: Keys to change.
        :raises ValueError: This group is a list of rows.
        """

        raise ValueError('This setting group is a list of rows and cannot be changed with set_system_settings.')


def setting_group(name: str) -> Section | Listing:
    """
    Return one System Explorer setting group.

    :param str name: ``units``, ``aperture``, ``fields``, ``wavelengths``, ``environment``, ``polarization``, or ``ray_aiming``.
    :returns: The group.
    :rtype: Section | Listing
    :raises ValueError: ``name`` is not a setting group.
    """

    try:
        return SYSTEM[name]
    except KeyError:
        choices = ', '.join(SYSTEM)
        raise ValueError(f'Unknown system setting group {name!r}. Expected one of: {choices}.') from None


def _enum_member(enumeration: str, key: str, value: str):
    # Resolve the enumeration on the ZOS-API thread, where ZOSAPI is already loaded.
    import clr
    import System
    import ZOSAPI

    enum = getattr(ZOSAPI.SystemData, enumeration)
    clr_type = clr.GetClrType(enum)
    names = list(System.Enum.GetNames(clr_type))

    if value not in names:
        choices = ', '.join(names)
        raise ValueError(f'{key} must be one of: {choices}.')

    return System.Enum.Parse(clr_type, value)


#: System Explorer setting groups, keyed by the name passed to OpticStudioSession.system_data.
SYSTEM: dict[str, Section | Listing] = {
    'units': Section(
        'Units',
        (
            Attribute('lens_units', 'LensUnits', str, enumeration='ZemaxSystemUnits'),
            Attribute('source_unit_prefix', 'SourceUnitPrefix', str, enumeration='ZemaxUnitPrefix'),
            Attribute('source_units', 'SourceUnits', str, enumeration='ZemaxSourceUnits'),
            Attribute('analysis_unit_prefix', 'AnalysisUnitPrefix', str, enumeration='ZemaxUnitPrefix'),
            Attribute('analysis_units', 'AnalysisUnits', str, enumeration='ZemaxAnalysisUnits'),
            Attribute('afocal_mode_units', 'AfocalModeUnits', str, enumeration='ZemaxAfocalModeUnits'),
            Attribute('mtf_units', 'MTFUnits', str, enumeration='ZemaxMTFUnits'),
        ),
    ),
    'aperture': Section(
        'Aperture',
        (
            Attribute('aperture_type', 'ApertureType', str, enumeration='ZemaxApertureType'),
            Attribute('aperture_value', 'ApertureValue', float),
            Attribute('apodization_type', 'ApodizationType', str, enumeration='ZemaxApodizationType'),
            Attribute('apodization_factor', 'ApodizationFactor', float),
            Attribute('apodization_factor_is_used', 'ApodizationFactorIsUsed', bool, writable=False),
            Attribute('semi_diameter_margin', 'SemiDiameterMargin', float),
            Attribute('semi_diameter_margin_percent', 'SemiDiameterMarginPct', float),
            Attribute('global_coordinate_reference_surface', ('GCRS', 'GetSelectedSurface'), int, call=True),
            Attribute('telecentric_object_space', 'TelecentricObjectSpace', bool),
            Attribute('afocal_image_space', 'AFocalImageSpace', bool),
            Attribute('iterate_solves_when_updating', 'IterateSolvesWhenUpdating', bool),
            Attribute('fast_semi_diameters', 'FastSemiDiameters', bool),
            Attribute('check_grin_apertures', 'CheckGRINApertures', bool),
        ),
    ),
    'fields': Section(
        'Fields',
        (
            Attribute('type', 'GetFieldType', str, call=True, enumeration='FieldType'),
            Attribute('normalization', 'Normalization', str, enumeration='FieldNormalizationType'),
        ),
        (
            (
                'points',
                Rows(
                    'NumberOfFields',
                    'GetField',
                    (
                        Attribute('number', 'FieldNumber', int),
                        Attribute('active', 'IsActive', bool),
                        Attribute('x', 'X', float),
                        Attribute('y', 'Y', float),
                        Attribute('weight', 'Weight', float),
                        Attribute('vdx', 'VDX', float),
                        Attribute('vdy', 'VDY', float),
                        Attribute('vcx', 'VCX', float),
                        Attribute('vcy', 'VCY', float),
                        Attribute('van', 'VAN', float),
                        Attribute('tan', 'TAN', float),
                        Attribute('comment', 'Comment', text),
                        Attribute('x_solve', 'XSolve', str),
                        Attribute('y_solve', 'YSolve', str),
                        Attribute('ignore', 'Ignore', bool),
                    ),
                ),
            ),
        ),
    ),
    'wavelengths': Listing(
        'Wavelengths',
        Rows(
            'NumberOfWavelengths',
            'GetWavelength',
            (
                Attribute('number', 'WavelengthNumber', int),
                Attribute('active', 'IsActive', bool),
                Attribute('wavelength', 'Wavelength', float),
                Attribute('weight', 'Weight', float),
                Attribute('primary', 'IsPrimary', bool),
            ),
        ),
    ),
    'environment': Section(
        'Environment',
        (
            Attribute('temperature', 'Temperature', float),
            Attribute('pressure', 'Pressure', float),
            Attribute('adjust_index_to_environment', 'AdjustIndexToEnvironment', bool),
        ),
    ),
    'polarization': Section(
        'Polarization',
        (
            Attribute('method', 'Method', str, enumeration='PolarizationMethod'),
            Attribute('unpolarized', 'Unpolarized', bool),
            Attribute('jx', 'Jx', float),
            Attribute('jy', 'Jy', float),
            Attribute('x_phase', 'XPhase', float),
            Attribute('y_phase', 'YPhase', float),
            Attribute('convert_thin_film_phase_to_ray_equivalent', 'ConvertThinFilmPhaseToRayEquivalent', bool),
        ),
    ),
    'ray_aiming': Section(
        'RayAiming',
        (
            Attribute('setting', 'RayAiming', str, enumeration='RayAimingMethod'),
            Attribute('method', 'Method', str, enumeration='RayAimingType'),
            Attribute('use_ray_aiming_cache', 'UseRayAimingCache', bool),
            Attribute('use_robust_ray_aiming', 'UseRobustRayAiming', bool),
            Attribute('scale_pupil_shift_factors_by_field', 'ScalePupilShiftFactorsByField', bool),
            Attribute('automatically_calculate_pupil_shifts', 'AutomaticallyCalculatePupilShiftsIsChecked', bool),
            Attribute('use_enhanced_ray_aiming', 'UseEnhancedRayAiming', bool),
            Attribute('use_advanced_convergence', 'UseAdvancedConvergence', bool),
            Attribute('use_fallback_search_during_cache_setup', 'UseFallBackSearchDuringCacheSetup', bool),
            Attribute('pupil_shift_x', 'PupilShiftX', float),
            Attribute('pupil_shift_y', 'PupilShiftY', float),
            Attribute('pupil_shift_z', 'PupilShiftZ', float),
            Attribute('pupil_compress_x', 'PupilCompressX', float),
            Attribute('pupil_compress_y', 'PupilCompressY', float),
            Attribute('cache_setup_steps', 'NumStepsCacheSetup', int),
        ),
    ),
}


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
