"""Merit Function Editor operands and calculation."""

import dataclasses
import math

from zaymcp.zosapi.errors import OpticStudioError
from zaymcp.zosapi.model.cells import _cell_for_write, _cell_value, _place_cell
from zaymcp.zosapi.model.fields import Attribute, text

__all__ = [
    'MERIT',
    'MeritFunction',
]

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


def _calculate_merit(editor) -> dict[str, object]:
    # Calculate before reading so value and contribution are the new results.
    try:
        raw = editor.CalculateMeritFunction()
    except OpticStudioError:
        raise
    except Exception as exc:
        raise ValueError(f'The merit function could not be calculated. {exc}') from exc

    number = float(raw)
    operands = MERIT.read(editor)

    return {
        'merit': number if math.isfinite(number) else None,
        'operands': operands['operands'],
    }
