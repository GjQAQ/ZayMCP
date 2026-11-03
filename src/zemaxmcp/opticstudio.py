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
import math
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
        :param dict[str, object] | None values: Keys to write. The fields are the same as those of one surface returned by :meth:`lens_data`. ``type`` changes the surface type first. ``parameters`` maps column names such as ``Par1`` to new values.
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

    def first_order(self) -> dict[str, float | str | None]:
        """
        Return first-order values for the lens open in the OpticStudio window.

        The system is updated first. Lengths are in lens units. ``working_f_number`` is the on-axis value at the primary wavelength. ``total_length`` runs from surface 1 to the image surface.

        :returns: Effective focal length, entrance pupil diameter, paraxial and working F-numbers, and total length. A number is ``None`` when OpticStudio does not return a finite value. ``status`` is empty when the update reports nothing.
        :rtype: dict[str, float | str | None]
        :raises OpticStudioError: The session is already closed, or OpticStudio cannot answer.
        """

        return self.call(lambda: _read_first_order(self._system))

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
    :param bool writable: When true, a write tool may change this member.
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
    #: When true, a write tool may change this member.
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

        if self.convert is text:
            if not isinstance(value, str):
                raise ValueError(f'{self.name} must be a string.')

            return value

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
    :param str | None add: Method that appends a row. ``None`` when rows cannot be added.
    :param add_arguments: Attribute names passed to ``add``, in order.
    :type add_arguments: tuple[str, ...]
    :param str | None remove: Method that removes a 1-based row. ``None`` when rows cannot be removed.
    :param str | None primary: Method on one row that makes it primary. ``None`` when the list has no primary row.
    """

    #: Property that holds the number of rows.
    count: str
    #: Method that returns one row. The argument is a 1-based index.
    item: str
    #: Attributes copied from each row.
    attributes: tuple[Attribute, ...]
    #: Method that appends a row. ``None`` when rows cannot be added.
    add: str | None = None
    #: Attribute names passed to ``add``, in order.
    add_arguments: tuple[str, ...] = ()
    #: Method that removes a 1-based row. ``None`` when rows cannot be removed.
    remove: str | None = None
    #: Method on one row that makes it primary. ``None`` when the list has no primary row.
    primary: str | None = None

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

    def edit(
        self,
        data,
        action: str,
        number: int | None,
        values: dict[str, object] | None,
    ) -> None:
        """
        Change, add, or remove one row.

        ``add`` appends a row. ``make_primary`` calls :attr:`primary` on the selected row.

        :param data: Object that exposes ``count`` and ``item``.
        :param str action: ``change``, ``add``, ``remove``, or ``make_primary``.
        :param int | None number: 1-based row. Required except for ``add``.
        :param dict[str, object] | None values: Keys to write. Names match :meth:`read`.
        :raises ValueError: The action, number, or values cannot be applied.
        """

        supplied = {} if values is None else values

        if action == 'add':
            self._add(data, number, supplied)

            return

        if action == 'change':
            self._change(data, number, supplied)

            return

        if action in ('remove', 'make_primary'):
            self._select(data, action, number, supplied)

            return

        raise ValueError("action must be 'change', 'add', 'remove', or 'make_primary'.")

    def _add(self, data, number: int | None, values: dict[str, object]) -> None:
        if self.add is None:
            raise ValueError('Rows cannot be added to this list.')

        if number is not None:
            raise ValueError('add appends a row and does not take a number.')

        missing = [key for key in self.add_arguments if key not in values]

        if missing:
            required = ', '.join(self.add_arguments)
            raise ValueError(f'add requires {required}.')

        prepared = self._prepare(values)
        extras = [(attribute, value) for attribute, value in prepared if attribute.name not in self.add_arguments]

        # Arguments follow add_arguments, not the order of values.
        by_name = {attribute.name: value for attribute, value in prepared}
        row = getattr(data, self.add)(*(by_name[key] for key in self.add_arguments))

        for attribute, value in extras:
            attribute._place(row, value)

    def _change(self, data, number: int | None, values: dict[str, object]) -> None:
        if not values:
            raise ValueError('values must contain the keys to change.')

        prepared = self._prepare(values)
        row = self._row(data, self._row_number(data, number))

        for attribute, value in prepared:
            attribute._place(row, value)

    def _select(self, data, action: str, number: int | None, values: dict[str, object]) -> None:
        if values:
            raise ValueError(f'{action} does not take values.')

        if action == 'make_primary':
            if self.primary is None:
                raise ValueError('This row list has no primary row.')

            row = self._row(data, self._row_number(data, number))
            getattr(row, self.primary)()

            return

        if self.remove is None:
            raise ValueError('Rows cannot be removed from this list.')

        row_number = self._row_number(data, number)
        removed = getattr(data, self.remove)(row_number)

        if removed is False:
            raise ValueError(f'Row {number} could not be removed.')

    def _prepare(self, values: dict[str, object]) -> list[tuple[Attribute, object]]:
        # Convert every value before changing a row, so a bad key leaves the row unchanged.
        by_name = {item.name: item for item in self.attributes}
        prepared = []

        for key, value in values.items():
            attribute = by_name.get(key)

            if attribute is None:
                allowed = ', '.join(item.name for item in self.attributes if item.writable)
                raise ValueError(f'Unknown setting {key!r}. Expected one of: {allowed}.')

            if not attribute.writable:
                if key == 'primary' and self.primary is not None:
                    raise ValueError('primary is read-only. Use make_primary.')

                raise ValueError(f'{key} is read-only.')

            prepared.append((attribute, attribute.value_for_write(value)))

        return prepared

    def _row(self, data, number: int):
        return getattr(data, self.item)(number)

    def _row_number(self, data, number: int | None) -> int:
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError('number is required.')

        total = int(getattr(data, self.count))

        if number < 1 or number > total:
            raise ValueError(f'number must be from 1 to {total}.')

        return number


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


def row_editor(name: str) -> tuple[str, Rows]:
    """
    Return the SystemData property and row list for one editable group.

    :param str name: ``fields`` or ``wavelengths``.
    :returns: The property name on SystemData, and the rows to edit.
    :rtype: tuple[str, Rows]
    :raises ValueError: ``name`` is not a setting group, or that group has no row list.
    """

    group = setting_group(name)
    editor = _row_editor(group)

    if editor is None:
        choices = ', '.join(label for label, item in SYSTEM.items() if _row_editor(item) is not None)
        raise ValueError(f'{name} has no row list. Expected one of: {choices}.')

    return editor


def _row_editor(group: Section | Listing) -> tuple[str, Rows] | None:
    # A listing is the row list. A section contributes its one editable collection.
    if isinstance(group, Listing) and group.rows.add is not None:
        return group.source, group.rows

    if isinstance(group, Section) and len(group.rows) == 1 and group.rows[0][1].add is not None:
        return group.source, group.rows[0][1]

    return None


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
                        Attribute('number', 'FieldNumber', int, writable=False),
                        Attribute('active', 'IsActive', bool, writable=False),
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
                        Attribute('x_solve', 'XSolve', str, writable=False),
                        Attribute('y_solve', 'YSolve', str, writable=False),
                        Attribute('ignore', 'Ignore', bool),
                    ),
                    'AddField',
                    ('x', 'y', 'weight'),
                    'RemoveField',
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
                Attribute('number', 'WavelengthNumber', int, writable=False),
                Attribute('active', 'IsActive', bool, writable=False),
                Attribute('wavelength', 'Wavelength', float),
                Attribute('weight', 'Weight', float),
                Attribute('primary', 'IsPrimary', bool, writable=False),
            ),
            'AddWavelength',
            ('wavelength', 'weight'),
            'RemoveWavelength',
            'MakePrimary',
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


# Parameter columns from Par0 upward. None until the first read on the ZOS-API thread.
_PARAMETER_COLUMNS: dict[str, object] | None = None


def _parameter_columns() -> dict[str, object]:
    # Resolved on the ZOS-API thread, where the enumeration is already loaded.
    global _PARAMETER_COLUMNS

    if _PARAMETER_COLUMNS is not None:
        return _PARAMETER_COLUMNS

    import clr
    import System
    import ZOSAPI

    enum = ZOSAPI.Editors.LDE.SurfaceColumn
    clr_type = clr.GetClrType(enum)
    numbered = []

    for name in System.Enum.GetNames(clr_type):
        label = str(name)

        if not label.startswith('Par'):
            continue

        member = getattr(enum, label)
        numbered.append((int(member), label, member))

    numbered.sort()
    _PARAMETER_COLUMNS = {label: member for _, label, member in numbered}

    return _PARAMETER_COLUMNS


def _surface_type_name(value: object) -> str:
    # ``SurfaceType`` lives on the lens data editor, not on SystemData.
    if not isinstance(value, str):
        raise ValueError('type must be a string.')

    import clr
    import System
    import ZOSAPI

    enum = ZOSAPI.Editors.LDE.SurfaceType
    clr_type = clr.GetClrType(enum)
    names = list(System.Enum.GetNames(clr_type))

    if value not in names:
        choices = ', '.join(names)
        raise ValueError(f'type must be one of: {choices}.')

    return value


def _active_cells(row) -> dict[str, object]:
    # Used parameter columns are contiguous. Par0 may be unused while Par1 is used.
    # When Par0 and Par1 are both unused, this surface type has no parameter columns.
    active = {}
    seen = 0

    for name, column in _parameter_columns().items():
        cell = row.GetSurfaceCell(column)
        seen += 1

        if bool(cell.IsActive):
            active[name] = cell

            continue

        if active or seen >= 2:
            break

    return active


def _cell_value(cell) -> object:
    kind = str(cell.DataType)

    if kind == 'Integer':
        return int(cell.IntegerValue)

    if kind == 'Double':
        return float(cell.DoubleValue)

    if kind == 'String':
        return text(cell.Value)

    raise ValueError(f'Unsupported cell data type {kind}.')


def _cell_for_write(cell, key: str, value: object) -> object:
    kind = str(cell.DataType)

    if kind == 'Integer':
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{key} must be an integer.')

        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f'{key} must be an integer.')

        return int(value)

    if kind == 'Double':
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{key} must be a number.')

        return float(value)

    if kind == 'String':
        if not isinstance(value, str):
            raise ValueError(f'{key} must be a string.')

        return value

    raise ValueError(f'{key} has unsupported data type {kind}.')


def _place_cell(cell, value: object) -> None:
    kind = str(cell.DataType)

    if kind == 'Integer':
        cell.IntegerValue = value

        return

    if kind == 'Double':
        cell.DoubleValue = value

        return

    cell.Value = value


@dataclasses.dataclass(frozen=True)
class LensData:
    """
    Lens Data Editor columns copied for every surface.

    Parameter columns depend on the surface type. :meth:`read` includes the active ones.

    :param attributes: Columns read from each surface.
    :type attributes: tuple[Attribute, ...]
    """

    #: Columns read from each surface.
    attributes: tuple[Attribute, ...]

    def read(self, editor, surface: int | None = None) -> dict[str, object]:
        """
        Read every surface, or one surface.

        :param editor: The ZOS-API lens data editor.
        :param int | None surface: One surface number. ``None`` reads every surface. 0 is the object surface.
        :returns: ``surfaces``, or the one requested surface. Each surface includes ``parameters`` for the columns its type uses.
        :rtype: dict[str, object]
        :raises ValueError: ``surface`` is outside the editor.
        """

        if surface is not None:
            index = self._surface_number(editor, surface, inserting=False)

            return self._surface(editor.GetSurfaceAt(index))

        total = int(editor.NumberOfSurfaces)
        surfaces = []

        for index in range(total):
            surfaces.append(self._surface(editor.GetSurfaceAt(index)))

        return {
            'surfaces': surfaces,
        }

    def edit(
        self,
        editor,
        action: str,
        number: int | None,
        values: dict[str, object] | None,
    ) -> None:
        """
        Change, insert, or remove one surface.

        ``add`` inserts at ``number`` and then writes ``values``. ``type`` changes the surface type before the other keys. ``parameters`` maps column names such as ``Par1`` to new values.

        :param editor: The ZOS-API lens data editor.
        :param str action: ``change``, ``add``, or ``remove``.
        :param int | None number: Surface number. 0 is the object surface.
        :param dict[str, object] | None values: Keys to write. The fields are the same as those returned by :meth:`read`.
        :raises ValueError: The action, number, or values cannot be applied.
        """

        supplied = {} if values is None else values

        if action == 'change':
            self._change(editor, number, supplied)

            return

        if action == 'add':
            self._add(editor, number, supplied)

            return

        if action == 'remove':
            self._remove(editor, number, supplied)

            return

        raise ValueError("action must be 'change', 'add', or 'remove'.")

    def _change(self, editor, number: int | None, values: dict[str, object]) -> None:
        if not values:
            raise ValueError('values must contain the keys to change.')

        surface_type, parameters, columns = self._prepare(values)
        index = self._surface_number(editor, number, inserting=False)
        row = editor.GetSurfaceAt(index)

        self._apply(row, surface_type, parameters, columns)

    def _add(self, editor, number: int | None, values: dict[str, object]) -> None:
        surface_type, parameters, columns = self._prepare(values)
        index = self._surface_number(editor, number, inserting=True)
        row = editor.InsertNewSurfaceAt(index)

        if row is None:
            raise ValueError(f'Surface {index} could not be inserted.')

        self._apply(row, surface_type, parameters, columns)

    def _remove(self, editor, number: int | None, values: dict[str, object]) -> None:
        if values:
            raise ValueError('remove does not take values.')

        index = self._surface_number(editor, number, inserting=False)
        row = editor.GetSurfaceAt(index)

        if bool(row.IsObject):
            raise ValueError('The object surface cannot be removed.')

        if bool(row.IsImage):
            raise ValueError('The image surface cannot be removed.')

        removed = editor.RemoveSurfaceAt(index)

        if removed is False:
            raise ValueError(f'Surface {index} could not be removed.')

    def _prepare(
        self,
        values: dict[str, object],
    ) -> tuple[str | None, dict[str, object] | None, list[tuple[Attribute, object]]]:
        # Convert every value before changing a surface, so a bad key leaves the editor unchanged.
        by_name = {item.name: item for item in self.attributes}
        surface_type = None
        parameters = None
        prepared = []

        for key, value in values.items():
            if key == 'type':
                surface_type = _surface_type_name(value)

                continue

            if key == 'parameters':
                parameters = self._parameter_values(value)

                continue

            attribute = by_name.get(key)

            if attribute is None:
                allowed = self._writable_names()
                raise ValueError(f'Unknown setting {key!r}. Expected one of: {allowed}.')

            if not attribute.writable:
                raise ValueError(f'{key} is read-only.')

            prepared.append((attribute, attribute.value_for_write(value)))

        return surface_type, parameters, prepared

    def _parameter_values(self, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValueError('parameters must be a dictionary of column names.')

        if not value:
            raise ValueError('parameters must contain the columns to change.')

        columns = _parameter_columns()
        prepared = {}

        for key, item in value.items():
            if key not in columns:
                raise ValueError(f'Unknown parameter column {key!r}. Expected a name such as Par1.')

            if isinstance(item, bool) or not isinstance(item, (int, float, str)):
                raise ValueError(f'{key} must be a number or a string.')

            prepared[key] = item

        return prepared

    def _writable_names(self) -> str:
        names = [item.name for item in self.attributes if item.name == 'type' or item.writable]

        names.append('parameters')

        return ', '.join(names)

    def _apply(
        self,
        row,
        surface_type: str | None,
        parameters: dict[str, object] | None,
        columns: list[tuple[Attribute, object]],
    ) -> None:
        # The surface type selects which parameter columns exist, so it changes before those columns are checked.
        if surface_type is not None:
            self._change_type(row, surface_type)

        converted = [] if parameters is None else self._converted_parameters(row, parameters)

        for attribute, value in columns:
            attribute._place(row, value)

        for cell, value in converted:
            _place_cell(cell, value)

    def _change_type(self, row, name: str) -> None:
        import ZOSAPI

        surface_type = getattr(ZOSAPI.Editors.LDE.SurfaceType, name)
        settings = row.GetSurfaceTypeSettings(surface_type)
        changed = row.ChangeType(settings)

        if changed is False:
            if bool(settings.RequiresFile):
                raise ValueError(f'Surface type {name} could not be applied. It requires a file.')

            raise ValueError(f'Surface type {name} could not be applied.')

    def _converted_parameters(self, row, parameters: dict[str, object]) -> list[tuple[object, object]]:
        active = _active_cells(row)
        converted = []

        for key, value in parameters.items():
            cell = active.get(key)

            if cell is None:
                choices = ', '.join(active) if active else 'none'
                raise ValueError(f'{key} is not used by this surface type. Expected one of: {choices}.')

            if bool(cell.IsReadOnly):
                raise ValueError(f'{key} is read-only.')

            converted.append((cell, _cell_for_write(cell, key, value)))

        return converted

    def _surface(self, row) -> dict[str, object]:
        record = Attribute.record(row, self.attributes)
        parameters = self._parameters(row)
        ordered = {}

        for key, value in record.items():
            ordered[key] = value

            if key == 'type':
                ordered['parameters'] = parameters

        return ordered

    def _parameters(self, row) -> list[dict[str, object]]:
        parameters = []

        for name, cell in _active_cells(row).items():
            parameters.append({
                'column': name,
                'header': text(cell.Header),
                'value': _cell_value(cell),
            })

        return parameters

    def _surface_number(self, editor, number: int | None, inserting: bool) -> int:
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError('number is required.')

        total = int(editor.NumberOfSurfaces)
        last = total - 1

        if inserting:
            if number < 1 or number > last:
                raise ValueError(f'number must be from 1 to {last}.')

            return number

        if number < 0 or number > last:
            raise ValueError(f'number must be from 0 to {last}.')

        return number


#: Columns copied from every Lens Data Editor surface.
LENS = LensData(
    (
        Attribute('surface_number', 'SurfaceNumber', int, writable=False),
        # Written by _change_type through ChangeType.
        Attribute('type', 'Type', str, writable=False),
        Attribute('comment', 'Comment', text),
        Attribute('radius', 'Radius', float),
        Attribute('thickness', 'Thickness', float),
        Attribute('material', 'Material', text),
        Attribute('coating', 'Coating', text),
        Attribute('semi_diameter', 'SemiDiameter', float),
        Attribute('chip_zone', 'ChipZone', float),
        Attribute('mechanical_semi_diameter', 'MechanicalSemiDiameter', float),
        Attribute('conic', 'Conic', float),
        Attribute('tce', 'TCE', float),
        Attribute('is_stop', 'IsStop', bool),
    ),
)


# Operand data columns from Param1 upward. None until the first read on the ZOS-API thread.
_MERIT_COLUMNS: dict[str, object] | None = None


def _merit_columns() -> dict[str, object]:
    # Resolved on the ZOS-API thread, where the enumeration is already loaded.
    global _MERIT_COLUMNS

    if _MERIT_COLUMNS is not None:
        return _MERIT_COLUMNS

    import clr
    import System
    import ZOSAPI

    enum = ZOSAPI.Editors.MFE.MeritColumn
    clr_type = clr.GetClrType(enum)
    numbered = []

    for name in System.Enum.GetNames(clr_type):
        label = str(name)

        if not label.startswith('Param'):
            continue

        member = getattr(enum, label)
        numbered.append((int(member), label, member))

    numbered.sort()
    _MERIT_COLUMNS = {label: member for _, label, member in numbered}

    return _MERIT_COLUMNS


def _operand_type_name(value: object) -> str:
    # MeritOperandType has several hundred members, so an unknown name is reported without listing them.
    if not isinstance(value, str):
        raise ValueError('type must be a string.')

    import clr
    import System
    import ZOSAPI

    enum = ZOSAPI.Editors.MFE.MeritOperandType
    clr_type = clr.GetClrType(enum)

    if not System.Enum.IsDefined(clr_type, value):
        raise ValueError(f'Unknown operand type {value!r}.')

    return value


def _active_operand_cells(row) -> dict[str, object]:
    # A data column is present only when this operand type uses it.
    active = {}

    for name, column in _merit_columns().items():
        cell = row.GetOperandCell(column)

        if bool(cell.IsActive):
            active[name] = cell

    return active


def _operand_comment_cell(row):
    import ZOSAPI

    return row.GetOperandCell(ZOSAPI.Editors.MFE.MeritColumn.Comment)


@dataclasses.dataclass(frozen=True)
class MeritFunction:
    """
    Merit Function Editor columns copied for every operand.

    Data columns depend on the operand type. :meth:`read` includes the active ones.

    :param attributes: Columns read from each operand.
    :type attributes: tuple[Attribute, ...]
    """

    #: Columns read from each operand.
    attributes: tuple[Attribute, ...]

    def read(self, editor, operand: int | None = None) -> dict[str, object]:
        """
        Read every operand, or one operand.

        :param editor: The ZOS-API merit function editor.
        :param int | None operand: One 1-based operand number. ``None`` reads every operand.
        :returns: ``operands``, or the one requested operand. Each operand includes ``parameters`` for the columns its type uses.
        :rtype: dict[str, object]
        :raises ValueError: ``operand`` is outside the editor.
        """

        if operand is not None:
            number = self._operand_number(editor, operand, inserting=False)

            return self._operand(editor.GetOperandAt(number))

        total = int(editor.NumberOfOperands)
        operands = []

        for number in range(1, total + 1):
            operands.append(self._operand(editor.GetOperandAt(number)))

        return {
            'operands': operands,
        }

    def edit(
        self,
        editor,
        action: str,
        number: int | None,
        values: dict[str, object] | None,
    ) -> None:
        """
        Change, insert, or remove one operand.

        ``add`` inserts at ``number`` and then writes ``values``. ``type`` changes the operand type before the other keys. ``parameters`` maps column names such as ``Param1`` to new values.

        :param editor: The ZOS-API merit function editor.
        :param str action: ``change``, ``add``, or ``remove``.
        :param int | None number: 1-based operand number.
        :param dict[str, object] | None values: Keys to write. The fields are the same as those returned by :meth:`read`.
        :raises ValueError: The action, number, or values cannot be applied.
        """

        supplied = {} if values is None else values

        if action == 'change':
            self._change(editor, number, supplied)

            return

        if action == 'add':
            self._add(editor, number, supplied)

            return

        if action == 'remove':
            self._remove(editor, number, supplied)

            return

        raise ValueError("action must be 'change', 'add', or 'remove'.")

    def _change(self, editor, number: int | None, values: dict[str, object]) -> None:
        if not values:
            raise ValueError('values must contain the keys to change.')

        operand_type, parameters, comment, columns = self._prepare(values)
        index = self._operand_number(editor, number, inserting=False)
        row = editor.GetOperandAt(index)

        self._apply(row, operand_type, parameters, comment, columns)

    def _add(self, editor, number: int | None, values: dict[str, object]) -> None:
        operand_type, parameters, comment, columns = self._prepare(values)
        index = self._operand_number(editor, number, inserting=True)
        total = int(editor.NumberOfOperands)

        if index == total + 1:
            row = editor.AddOperand()
        else:
            row = editor.InsertNewOperandAt(index)

        if row is None:
            raise ValueError(f'Operand {index} could not be inserted.')

        self._apply(row, operand_type, parameters, comment, columns)

    def _remove(self, editor, number: int | None, values: dict[str, object]) -> None:
        if values:
            raise ValueError('remove does not take values.')

        index = self._operand_number(editor, number, inserting=False)
        removed = editor.RemoveOperandAt(index)

        if removed is False:
            raise ValueError(f'Operand {index} could not be removed.')

    def _prepare(
        self,
        values: dict[str, object],
    ) -> tuple[str | None, dict[str, object] | None, str | None, list[tuple[Attribute, object]]]:
        # Convert every value before changing an operand, so a bad key leaves the editor unchanged.
        by_name = {item.name: item for item in self.attributes}
        operand_type = None
        parameters = None
        comment = None
        prepared = []

        for key, value in values.items():
            if key == 'type':
                operand_type = _operand_type_name(value)

                continue

            if key == 'parameters':
                parameters = self._parameter_values(value)

                continue

            if key == 'comment':
                if not isinstance(value, str):
                    raise ValueError('comment must be a string.')

                comment = value

                continue

            attribute = by_name.get(key)

            if attribute is None:
                allowed = self._writable_names()
                raise ValueError(f'Unknown setting {key!r}. Expected one of: {allowed}.')

            if not attribute.writable:
                raise ValueError(f'{key} is read-only.')

            prepared.append((attribute, attribute.value_for_write(value)))

        return operand_type, parameters, comment, prepared

    def _parameter_values(self, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValueError('parameters must be a dictionary of column names.')

        if not value:
            raise ValueError('parameters must contain the columns to change.')

        columns = _merit_columns()
        prepared = {}

        for key, item in value.items():
            if key not in columns:
                raise ValueError(f'Unknown parameter column {key!r}. Expected a name such as Param1.')

            if isinstance(item, bool) or not isinstance(item, (int, float, str)):
                raise ValueError(f'{key} must be a number or a string.')

            prepared[key] = item

        return prepared

    def _writable_names(self) -> str:
        names = []

        for item in self.attributes:
            if item.name == 'type' or item.writable:
                names.append(item.name)

            if item.name == 'type':
                names.append('parameters')

        names.append('comment')

        return ', '.join(names)

    def _apply(
        self,
        row,
        operand_type: str | None,
        parameters: dict[str, object] | None,
        comment: str | None,
        columns: list[tuple[Attribute, object]],
    ) -> None:
        # The operand type selects which data columns exist, so it changes before those columns are checked.
        if operand_type is not None:
            self._change_type(row, operand_type)

        converted = [] if parameters is None else self._converted_parameters(row, parameters)
        comment_cell = None if comment is None else self._comment_for_write(row, comment)

        for attribute, value in columns:
            attribute._place(row, value)

        for cell, value in converted:
            _place_cell(cell, value)

        if comment_cell is not None:
            cell, value = comment_cell
            _place_cell(cell, value)

    def _change_type(self, row, name: str) -> None:
        import ZOSAPI

        operand_type = getattr(ZOSAPI.Editors.MFE.MeritOperandType, name)
        changed = row.ChangeType(operand_type)

        if changed is False:
            raise ValueError(f'Operand type {name} could not be applied.')

    def _converted_parameters(self, row, parameters: dict[str, object]) -> list[tuple[object, object]]:
        active = _active_operand_cells(row)
        converted = []

        for key, value in parameters.items():
            cell = active.get(key)

            if cell is None:
                choices = ', '.join(active) if active else 'none'
                raise ValueError(f'{key} is not used by this operand type. Expected one of: {choices}.')

            if bool(cell.IsReadOnly):
                raise ValueError(f'{key} is read-only.')

            converted.append((cell, _cell_for_write(cell, key, value)))

        return converted

    def _comment_for_write(self, row, comment: str) -> tuple[object, object]:
        cell = _operand_comment_cell(row)

        if not bool(cell.IsActive):
            raise ValueError('comment is not used by this operand.')

        if bool(cell.IsReadOnly):
            raise ValueError('comment is read-only.')

        return cell, _cell_for_write(cell, 'comment', comment)

    def _operand(self, row) -> dict[str, object]:
        record = Attribute.record(row, self.attributes)
        parameters = self._parameters(row)
        ordered = {}

        for key, value in record.items():
            ordered[key] = value

            if key == 'type':
                ordered['parameters'] = parameters

        ordered['comment'] = self._comment(row)

        return ordered

    def _parameters(self, row) -> list[dict[str, object]]:
        parameters = []

        for name, cell in _active_operand_cells(row).items():
            parameters.append({
                'column': name,
                'header': text(cell.Header),
                'value': _cell_value(cell),
            })

        return parameters

    def _comment(self, row) -> str:
        cell = _operand_comment_cell(row)

        if not bool(cell.IsActive):
            return ''

        value = _cell_value(cell)

        if isinstance(value, str):
            return value

        return text(value)

    def _operand_number(self, editor, number: int | None, inserting: bool) -> int:
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError('number is required.')

        total = int(editor.NumberOfOperands)

        if inserting:
            if number < 1 or number > total + 1:
                raise ValueError(f'number must be from 1 to {total + 1}.')

            return number

        if total == 0:
            raise ValueError('The merit function has no operands.')

        if number < 1 or number > total:
            raise ValueError(f'number must be from 1 to {total}.')

        return number


#: Columns copied from every Merit Function Editor operand.
MERIT = MeritFunction(
    (
        Attribute('number', 'OperandNumber', int, writable=False),
        Attribute('active', 'IsActive', bool, writable=False),
        # Written by _change_type through ChangeType.
        Attribute('type', 'Type', str, writable=False),
        Attribute('target', 'Target', float),
        Attribute('weight', 'Weight', float),
        Attribute('value', 'Value', float, writable=False),
        Attribute('contribution', 'Contribution', float, writable=False),
    ),
)


# Name, operand, and the two integer arguments. Wave 0 selects the primary wavelength.
# TOTR starts at surface 1; a second integer of 0 ends at the image surface.
_FIRST_ORDER: tuple[tuple[str, str, int, int], ...] = (
    ('effective_focal_length', 'EFFL', 0, 0),
    ('entrance_pupil_diameter', 'EPDI', 0, 0),
    ('image_space_f_number', 'ISFN', 0, 0),
    ('working_f_number', 'WFNO', 0, 0),
    ('total_length', 'TOTR', 1, 0),
)


def _read_first_order(system) -> dict[str, float | str | None]:
    # Update first so the operands see the latest solves.
    status = text(system.UpdateStatus())
    editor = system.MFE

    import ZOSAPI

    operand = ZOSAPI.Editors.MFE.MeritOperandType
    values: dict[str, float | str | None] = {}

    for name, kind, surf, wave in _FIRST_ORDER:
        raw = editor.GetOperandValue(getattr(operand, kind), surf, wave, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        number = float(raw)
        values[name] = number if math.isfinite(number) else None

    values['status'] = status

    return values


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
