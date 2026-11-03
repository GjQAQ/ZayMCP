"""Shared descriptions of ZOS-API members and row lists."""

import collections
import dataclasses

__all__ = [
    'Attribute',
    'Listing',
    'Rows',
    'Section',
    'text',
]

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
