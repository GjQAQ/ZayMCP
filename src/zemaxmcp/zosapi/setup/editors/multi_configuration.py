"""Multi-Configuration Editor operands and configuration columns."""

from zemaxmcp.zosapi.model.cells import (
    _UNSET,
    _apply_solve,
    _cell_for_write,
    _cell_value,
    _cell_write,
    _place_cell,
    _read_solve,
    _whole_number,
)

__all__ = [
    'MULTI',
    'MultiConfiguration',
]

class MultiConfiguration:
    """
    Multi-Configuration Editor operands and configuration columns.

    Parameter columns and configuration cells depend on the operand type.
    """

    def read(self, editor, operand: int | None = None) -> dict[str, object]:
        """
        Read the editor, or one operand.

        :param editor: The ZOS-API multi-configuration editor.
        :param int | None operand: One 1-based operand number. ``None`` reads the whole editor.
        :returns: ``current``, ``configurations``, and ``operands``, or the one requested operand.
        :rtype: dict[str, object]
        :raises ValueError: ``operand`` is outside the editor.
        """

        if operand is not None:
            number = self._operand_number(editor, operand, inserting=False)

            return self._operand(editor, editor.GetOperandAt(number))

        operands = []

        for number in range(1, int(editor.NumberOfOperands) + 1):
            operands.append(self._operand(editor, editor.GetOperandAt(number)))

        return {
            'current': int(editor.CurrentConfiguration),
            'configurations': [{'number': number} for number in _configuration_numbers(editor)],
            'operands': operands,
        }

    def edit(
        self,
        editor,
        section: str,
        action: str,
        number: int | None,
        values: dict[str, object] | None,
    ) -> None:
        """
        Change one operand or one configuration.

        ``type`` changes the operand type before parameters and configuration cells are checked.

        :param editor: The ZOS-API multi-configuration editor.
        :param str section: ``operand`` or ``configuration``.
        :param str action: ``change``, ``add``, ``remove``, or ``make_current``.
        :param int | None number: 1-based operand or configuration number.
        :param dict[str, object] | None values: Keys to write.
        :raises ValueError: The section, action, number, or values cannot be applied.
        """

        if section == 'operand':
            self._edit_operand(editor, action, number, {} if values is None else values)

            return

        if section == 'configuration':
            self._edit_configuration(editor, action, number, {} if values is None else values)

            return

        raise ValueError("section must be 'operand' or 'configuration'.")

    def _operand(self, editor, row) -> dict[str, object]:
        return {
            'number': int(row.OperandNumber),
            'active': bool(row.IsActive),
            'type': str(row.Type),
            'parameters': self._parameters(row),
            'cells': self._cells(editor, row),
        }

    def _parameters(self, row) -> list[dict[str, object]]:
        parameters = []

        for name in _MCE_PARAMETERS:
            if not bool(getattr(row, name + 'Enabled')):
                continue

            parameters.append({
                'column': name,
                'value': int(getattr(row, name)),
            })

        return parameters

    def _cells(self, editor, row) -> list[dict[str, object]]:
        cells = []

        for number in _configuration_numbers(editor):
            cell = row.GetOperandCell(number)
            cells.append({
                'configuration': number,
                'value': _cell_value(cell),
                'solve': _read_solve(cell),
            })

        return cells

    def _edit_operand(self, editor, action: str, number: int | None, values: dict[str, object]) -> None:
        if action == 'change':
            self._change_operand(editor, number, values)

            return

        if action == 'add':
            self._add_operand(editor, number, values)

            return

        if action == 'remove':
            self._remove_operand(editor, number, values)

            return

        if action == 'make_current':
            raise ValueError("make_current selects a configuration.")

        raise ValueError("action must be 'change', 'add', 'remove', or 'make_current'.")

    def _change_operand(self, editor, number: int | None, values: dict[str, object]) -> None:
        if not values:
            raise ValueError('values must contain the keys to change.')

        operand_type, parameters, cells = self._prepare(values)
        index = self._operand_number(editor, number, inserting=False)
        self._apply(editor, editor.GetOperandAt(index), operand_type, parameters, cells)

    def _add_operand(self, editor, number: int | None, values: dict[str, object]) -> None:
        operand_type, parameters, cells = self._prepare(values)
        index = self._operand_number(editor, number, inserting=True)
        total = int(editor.NumberOfOperands)

        if index == total + 1:
            row = editor.AddOperand()
        else:
            row = editor.InsertNewOperandAt(index)

        if row is None:
            raise ValueError(f'Operand {index} could not be inserted.')

        self._apply(editor, row, operand_type, parameters, cells)

    def _remove_operand(self, editor, number: int | None, values: dict[str, object]) -> None:
        if values:
            raise ValueError('remove does not accept values.')

        index = self._operand_number(editor, number, inserting=False)

        if editor.RemoveOperandAt(index) is False:
            raise ValueError(f'Operand {index} could not be removed.')

    def _edit_configuration(self, editor, action: str, number: int | None, values: dict[str, object]) -> None:
        if action == 'change':
            raise ValueError('A configuration has no fields to change. Use make_current to select it.')

        if action == 'add':
            self._add_configuration(editor, number, values)

            return

        if action == 'remove':
            self._remove_configuration(editor, number, values)

            return

        if action == 'make_current':
            self._make_current(editor, number, values)

            return

        raise ValueError("action must be 'change', 'add', 'remove', or 'make_current'.")

    def _add_configuration(self, editor, number: int | None, values: dict[str, object]) -> None:
        copy = self._copy_flag(values)
        index = self._configuration_number(editor, number, inserting=True)
        numbers = _configuration_numbers(editor)
        appended = not numbers or index == numbers[-1] + 1
        added = editor.AddConfiguration(copy) if appended else editor.InsertConfiguration(index, copy)

        if added is False:
            raise ValueError(f'Configuration {index} could not be inserted.')

    def _remove_configuration(self, editor, number: int | None, values: dict[str, object]) -> None:
        if values:
            raise ValueError('remove does not accept values.')

        if len(_configuration_numbers(editor)) < 2:
            raise ValueError('The last configuration cannot be removed.')

        index = self._configuration_number(editor, number, inserting=False)

        if editor.DeleteConfiguration(index) is False:
            raise ValueError(f'Configuration {index} could not be removed.')

    def _make_current(self, editor, number: int | None, values: dict[str, object]) -> None:
        if values:
            raise ValueError('make_current does not accept values.')

        index = self._configuration_number(editor, number, inserting=False)

        if editor.SetCurrentConfiguration(index) is False:
            raise ValueError(f'Configuration {index} could not be selected.')

    def _prepare(
        self,
        values: dict[str, object],
    ) -> tuple[str | None, dict[str, int] | None, dict[int, tuple[object, dict[str, object] | None]] | None]:
        if not isinstance(values, dict):
            raise ValueError('values must be the operand fields to change.')

        operand_type = None
        parameters = None
        cells = None

        for key, value in values.items():
            if key == 'type':
                operand_type = _multi_config_type(value)

                continue

            if key == 'parameters':
                parameters = self._parameter_values(value)

                continue

            if key == 'cells':
                cells = self._cell_values(value)

                continue

            if key in ('number', 'active'):
                raise ValueError(f'{key} is read-only.')

            raise ValueError(f'Unknown setting {key!r}. Expected one of: type, parameters, cells.')

        return operand_type, parameters, cells

    def _apply(
        self,
        editor,
        row,
        operand_type: str | None,
        parameters: dict[str, int] | None,
        cells: dict[int, tuple[object, dict[str, object] | None]] | None,
    ) -> None:
        # The operand type selects which parameters and cell types exist, so it changes first.
        if operand_type is not None:
            self._change_type(row, operand_type)

        converted_parameters = [] if parameters is None else self._converted_parameters(row, parameters)
        converted_cells = [] if cells is None else self._converted_cells(editor, row, cells)

        for name, value in converted_parameters:
            setattr(row, name, value)

        for cell, value, solve in converted_cells:
            if value is not _UNSET:
                _place_cell(cell, value)

            if solve is not None:
                _apply_solve(cell, solve)

    def _change_type(self, row, name: str) -> None:
        import ZOSAPI

        changed = row.ChangeType(getattr(ZOSAPI.Editors.MCE.MultiConfigOperandType, name))

        if changed is False:
            raise ValueError(f'Operand type {name} could not be applied.')

    def _parameter_values(self, value: object) -> dict[str, int]:
        if not isinstance(value, dict) or not value:
            raise ValueError('parameters must contain the columns to change.')

        prepared = {}

        for key, item in value.items():
            if key not in _MCE_PARAMETERS:
                raise ValueError(f'Unknown parameter column {key!r}. Expected Param1, Param2, or Param3.')

            prepared[key] = _whole_number(key, item)

        return prepared

    def _cell_values(self, value: object) -> dict[int, tuple[object, dict[str, object] | None]]:
        if not isinstance(value, dict) or not value:
            raise ValueError('cells must contain the configurations to change.')

        prepared = {}

        for key, item in value.items():
            number = _configuration_key(key)
            prepared[number] = _cell_write(f'Configuration {number}', item)

        return prepared

    def _converted_parameters(self, row, parameters: dict[str, int]) -> list[tuple[str, int]]:
        converted = []

        for name, value in parameters.items():
            if not bool(getattr(row, name + 'Enabled')):
                raise ValueError(f'{name} is not used by this operand type.')

            converted.append((name, value))

        return converted

    def _converted_cells(
        self,
        editor,
        row,
        cells: dict[int, tuple[object, dict[str, object] | None]],
    ) -> list[tuple[object, object, dict[str, object] | None]]:
        numbers = set(_configuration_numbers(editor))
        converted = []

        for number, (value, solve) in cells.items():
            if number not in numbers:
                raise ValueError(f'Configuration {number} is not in the editor.')

            cell = row.GetOperandCell(number)

            if value is not _UNSET and bool(cell.IsReadOnly):
                raise ValueError(f'Configuration {number} is read-only.')

            stored = _UNSET if value is _UNSET else _cell_for_write(cell, f'Configuration {number}', value)
            converted.append((cell, stored, solve))

        return converted

    def _operand_number(self, editor, number: int | None, inserting: bool) -> int:
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError('number is required.')

        total = int(editor.NumberOfOperands)

        if inserting:
            if number < 1 or number > total + 1:
                raise ValueError(f'number must be from 1 to {total + 1}.')

            return number

        if total == 0:
            raise ValueError('The multi-configuration editor has no operands.')

        if number < 1 or number > total:
            raise ValueError(f'number must be from 1 to {total}.')

        return number

    def _configuration_number(self, editor, number: int | None, inserting: bool) -> int:
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError('number is required.')

        numbers = _configuration_numbers(editor)

        if inserting:
            if not numbers:
                if number != 1:
                    raise ValueError('number must be 1.')

                return number

            end = numbers[-1] + 1

            if number < numbers[0] or number > end:
                raise ValueError(f'number must be from {numbers[0]} to {end}.')

            return number

        if number not in numbers:
            shown = ', '.join(str(item) for item in numbers)
            raise ValueError(f'number must be one of: {shown}.')

        return number

    def _copy_flag(self, values: dict[str, object]) -> bool:
        if not isinstance(values, dict):
            raise ValueError('values must be the configuration fields to change.')

        if not values:
            return False

        if set(values) != {'copy'}:
            raise ValueError('A new configuration only accepts copy.')

        copy = values['copy']

        if not isinstance(copy, bool):
            raise ValueError('copy must be a boolean.')

        return copy


def _configuration_numbers(editor) -> list[int]:
    first = int(editor.FirstConfiguration)
    last = int(editor.LastConfiguration)

    if last < first:
        return []

    return list(range(first, last + 1))


def _configuration_key(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value

    if isinstance(value, str) and value.isdecimal():
        return int(value)

    raise ValueError(f'Unknown configuration {value!r}. Expected a configuration number.')


def _multi_config_type(value: object) -> str:
    # MultiConfigOperandType has more than a hundred members, so an unknown name is reported without listing them.
    if not isinstance(value, str):
        raise ValueError('type must be a string.')

    import clr
    import System
    import ZOSAPI

    enum = ZOSAPI.Editors.MCE.MultiConfigOperandType
    clr_type = clr.GetClrType(enum)

    if not System.Enum.IsDefined(clr_type, value):
        raise ValueError(f'Unknown operand type {value!r}.')

    return value


#: Parameter columns on a Multi-Configuration Editor operand, in editor order.
_MCE_PARAMETERS: tuple[str, ...] = ('Param1', 'Param2', 'Param3')

#: Multi-Configuration Editor operands and configuration columns.
MULTI = MultiConfiguration()
