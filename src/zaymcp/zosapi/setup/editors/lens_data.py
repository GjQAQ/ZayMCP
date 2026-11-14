"""Lens Data Editor columns and row edits."""

import dataclasses
import math

from zaymcp.zosapi.model.cells import (
    _UNSET,
    _apply_solve,
    _cell_for_write,
    _cell_value,
    _cell_write,
    _place_cell,
    _read_solve,
    _replay_solve,
    _solve_request,
)
from zaymcp.zosapi.model.fields import Attribute, text

__all__ = [
    'LENS',
    'LensData',
]

# Parameter columns from Par0 upward. None until the first read on the ZOS-API thread.
_PARAMETER_COLUMNS: dict[str, object] | None = None

#: Text used for an infinite radius or thickness.
_INFINITY: str = 'Infinity'

#: Lens Data columns that accept ``Infinity``.
_INFINITE_LENGTHS: frozenset[str] = frozenset(('radius', 'thickness'))


def _length_value(value: object) -> float | str:
    # OpticStudio returns a non-finite double for an infinite radius or thickness.
    number = float(value)

    if not math.isfinite(number):
        return _INFINITY

    return number


def _surface_length(name: str, value: object) -> float:
    # A radius of 0 is infinite. A thickness of 0 is a real zero.
    if value == _INFINITY:
        if name == 'radius':
            return 0.0

        return math.inf

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a number or "{_INFINITY}".')

    return float(value)


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


def _tce_used(row) -> bool:
    # The column exists on every surface, so IsActive stays true.
    # A catalog glass grays the cell out and IsReadOnly becomes true. The cell then displays "-".
    cell = row.TCECell

    return bool(cell.IsActive) and not bool(cell.IsReadOnly)


_LENS_SOLVE_COLUMNS: dict[str, str] = {
    'radius': 'RadiusCell',
    'thickness': 'ThicknessCell',
    'material': 'MaterialCell',
    'coating': 'CoatingCell',
    'semi_diameter': 'SemiDiameterCell',
    'chip_zone': 'ChipZoneCell',
    'mechanical_semi_diameter': 'MechanicalSemiDiameterCell',
    'conic': 'ConicCell',
    'tce': 'TCECell',
}


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
        :returns: ``surfaces``, or the one requested surface. Each surface includes ``parameters`` for the columns its type uses. The image surface omits ``thickness`` and ``thickness_solve``. ``tce`` and ``tce_solve`` are omitted when the surface does not use the TCE column.
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

        surface_type, parameters, solves, columns = self._prepare(values)
        index = self._surface_number(editor, number, inserting=False)
        row = editor.GetSurfaceAt(index)

        if bool(row.IsImage) and 'thickness' in solves:
            raise ValueError('The image surface has no thickness.')

        self._apply(row, surface_type, parameters, solves, columns)

    def _add(self, editor, number: int | None, values: dict[str, object]) -> None:
        surface_type, parameters, solves, columns = self._prepare(values)
        index = self._surface_number(editor, number, inserting=True)
        # InsertNewSurfaceAt copies the surface that moves down, including the image radius of curvature.
        kept = [self._capture(editor.GetSurfaceAt(i)) for i in range(int(editor.NumberOfSurfaces))]
        row = editor.InsertNewSurfaceAt(index)

        if row is None:
            raise ValueError(f'Surface {index} could not be inserted.')

        self._blank(row)

        for old_index, captured in enumerate(kept):
            new_index = old_index if old_index < index else old_index + 1
            self._restore(editor.GetSurfaceAt(new_index), captured)

        self._apply(row, surface_type, parameters, solves, columns)

    def _capture(self, row) -> dict[str, object]:
        solves = {}
        owned = set()

        for name, cell_name in _LENS_SOLVE_COLUMNS.items():
            if name == 'tce' and not _tce_used(row):
                continue

            read = _read_solve(getattr(row, cell_name))
            request = _replay_solve(read)

            if request is None:
                # None is an empty solve. The cell value is still stored on the surface.
                if read.get('type') != 'None':
                    owned.add(name)

                continue

            solves[name] = request

        columns = []

        for attribute in self.attributes:
            if not attribute.writable or attribute.name in owned:
                continue

            if attribute.name == 'thickness' and bool(row.IsImage):
                continue

            if attribute.name == 'tce' and not _tce_used(row):
                continue

            value = attribute.read(row)

            if attribute.name == 'is_stop' and not value:
                continue

            if attribute.name in _INFINITE_LENGTHS:
                value = _surface_length(attribute.name, value)

            columns.append((attribute, value))

        parameters = {}

        for item in self._parameters(row):
            read = item['solve']
            request = _replay_solve(read)

            if request is None and read.get('type') != 'None':
                continue

            parameters[str(item['column'])] = (item['value'], request)

        return {
            'type': str(row.Type),
            'parameters': parameters or None,
            'solves': solves,
            'columns': columns,
        }

    def _restore(self, row, captured: dict[str, object]) -> None:
        if str(row.Type) != captured['type']:
            self._change_type(row, str(captured['type']))

        self._apply(row, None, captured['parameters'], captured['solves'], captured['columns'])

    def _blank(self, row) -> None:
        # The inserted surface is a new Standard surface. Its radius is infinite and its thickness is zero.
        by_name = {item.name: item for item in self.attributes}
        columns = [
            (by_name['comment'], ''),
            (by_name['radius'], 0.0),
            (by_name['thickness'], 0.0),
            (by_name['material'], ''),
            (by_name['coating'], ''),
            (by_name['conic'], 0.0),
            (by_name['tce'], 0.0),
        ]
        # Coating has no solve. Semi-diameter, chip zone, and mechanical semi-diameter stay automatic.
        solves = {
            name: {'type': 'Fixed'}
            for name in ('radius', 'thickness', 'material', 'conic', 'tce')
        }

        self._change_type(row, 'Standard')
        self._apply(row, None, None, solves, columns)

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
    ) -> tuple[
        str | None,
        dict[str, tuple[object, dict[str, object] | None]] | None,
        dict[str, dict[str, object]],
        list[tuple[Attribute, object]],
    ]:
        # Convert every value before changing a surface, so a bad key leaves the editor unchanged.
        by_name = {item.name: item for item in self.attributes}
        surface_type = None
        parameters = None
        solves = {}
        prepared = []

        for key, value in values.items():
            if value is None:
                raise ValueError(f'{key} cannot be null.')

            if key in _INFINITE_LENGTHS:
                attribute = by_name.get(key)

                if attribute is None:
                    allowed = self._writable_names()
                    raise ValueError(f'Unknown setting {key!r}. Expected one of: {allowed}.')

                prepared.append((attribute, _surface_length(key, value)))

                continue

            if key == 'type':
                surface_type = _surface_type_name(value)

                continue

            if key == 'parameters':
                parameters = self._parameter_values(value)

                continue

            if key.endswith('_solve') and key[: -len('_solve')] in _LENS_SOLVE_COLUMNS:
                solves[key[: -len('_solve')]] = _solve_request(value)

                continue

            attribute = by_name.get(key)

            if attribute is None:
                allowed = self._writable_names()
                raise ValueError(f'Unknown setting {key!r}. Expected one of: {allowed}.')

            if not attribute.writable:
                raise ValueError(f'{key} is read-only.')

            prepared.append((attribute, attribute.value_for_write(value)))

        return surface_type, parameters, solves, prepared

    def _parameter_values(self, value: object) -> dict[str, tuple[object, dict[str, object] | None]]:
        if not isinstance(value, dict):
            raise ValueError('parameters must be a dictionary of column names.')

        if not value:
            raise ValueError('parameters must contain the columns to change.')

        columns = _parameter_columns()
        prepared = {}

        for key, item in value.items():
            if key not in columns:
                raise ValueError(f'Unknown parameter column {key!r}. Expected a name such as Par1.')

            prepared[key] = _cell_write(key, item)

        return prepared

    def _writable_names(self) -> str:
        names = [item.name for item in self.attributes if item.name == 'type' or item.writable]

        names.append('parameters')
        names.extend(f'{name}_solve' for name in _LENS_SOLVE_COLUMNS)

        return ', '.join(names)

    def _apply(
        self,
        row,
        surface_type: str | None,
        parameters: dict[str, tuple[object, dict[str, object] | None]] | None,
        solves: dict[str, dict[str, object]],
        columns: list[tuple[Attribute, object]],
    ) -> None:
        # The image surface has no following surface, and OpticStudio ignores a thickness written there.
        if any(attribute.name == 'thickness' for attribute, _value in columns) and bool(row.IsImage):
            raise ValueError('The image surface has no thickness.')

        # The surface type selects which parameter columns exist, so it changes before those columns are checked.
        if surface_type is not None:
            self._change_type(row, surface_type)

        converted = [] if parameters is None else self._converted_parameters(row, parameters)
        tce_columns = []
        other_columns = []

        for attribute, value in columns:
            if attribute.name == 'tce':
                tce_columns.append((attribute, value))
            else:
                other_columns.append((attribute, value))

        for attribute, value in other_columns:
            attribute._place(row, value)

        for cell, value, solve in converted:
            if value is not _UNSET:
                _place_cell(cell, value)

            if solve is not None:
                _apply_solve(cell, solve)

        # Material is written first. A catalog glass then turns the TCE column off.
        if (tce_columns or 'tce' in solves) and not _tce_used(row):
            raise ValueError('tce is not used by this surface.')

        for attribute, value in tce_columns:
            attribute._place(row, value)

        for name, request in solves.items():
            _apply_solve(getattr(row, _LENS_SOLVE_COLUMNS[name]), request)

    def _change_type(self, row, name: str) -> None:
        import ZOSAPI

        surface_type = getattr(ZOSAPI.Editors.LDE.SurfaceType, name)
        settings = row.GetSurfaceTypeSettings(surface_type)
        changed = row.ChangeType(settings)

        if changed is False:
            if bool(settings.RequiresFile):
                raise ValueError(f'Surface type {name} could not be applied. It requires a file.')

            raise ValueError(f'Surface type {name} could not be applied.')

    def _converted_parameters(
        self,
        row,
        parameters: dict[str, tuple[object, dict[str, object] | None]],
    ) -> list[tuple[object, object, dict[str, object] | None]]:
        active = _active_cells(row)
        converted = []

        for key, (value, solve) in parameters.items():
            cell = active.get(key)

            if cell is None:
                choices = ', '.join(active) if active else 'none'
                raise ValueError(f'{key} is not used by this surface type. Expected one of: {choices}.')

            if value is not _UNSET and bool(cell.IsReadOnly):
                raise ValueError(f'{key} is read-only.')

            stored = _UNSET if value is _UNSET else _cell_for_write(cell, key, value)
            converted.append((cell, stored, solve))

        return converted

    def _surface(self, row) -> dict[str, object]:
        # The image surface has no following surface, so it has no thickness column.
        attributes = self.attributes

        if bool(row.IsImage):
            attributes = tuple(item for item in attributes if item.name != 'thickness')

        record = Attribute.record(row, attributes)
        parameters = self._parameters(row)
        ordered = {}

        for key, value in record.items():
            if key == 'tce' and not _tce_used(row):
                continue

            ordered[key] = value

            if key in _LENS_SOLVE_COLUMNS:
                ordered[f'{key}_solve'] = _read_solve(getattr(row, _LENS_SOLVE_COLUMNS[key]))

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
                'solve': _read_solve(cell),
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
        Attribute('radius', 'Radius', _length_value),
        Attribute('thickness', 'Thickness', _length_value),
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
