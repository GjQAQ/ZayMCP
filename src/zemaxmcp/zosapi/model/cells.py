"""Cell values and solves shared by the editors."""

import dataclasses

from zemaxmcp.zosapi.model.fields import text

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


#: Missing cell value. Distinct from a stored number.
_UNSET: object = object()

#: Solve types that can be read and written, in the order shown to a caller.
_SOLVE_TYPES: tuple[str, ...] = (
    'Variable',
    'Fixed',
    'SurfacePickup',
    'FNumber',
    'Position',
    'ConfigPickup',
    'ThermalPickup',
)


@dataclasses.dataclass(frozen=True)
class _SolveField:
    """One parameter of a solve type."""

    #: Key in the solve object.
    name: str
    #: Property on the ZOS-API solve data.
    source: str
    #: ``int``, ``float``, or ``column``.
    kind: str
    #: Property that must be true before this field is used. Empty when the field is always used.
    capability: str = ''
    #: When false, the field may be omitted.
    required: bool = True


#: Parameters of each supported solve, in the order they are returned.
_SOLVE_FIELDS: dict[str, tuple[_SolveField, ...]] = {
    'Variable': (),
    'Fixed': (),
    'SurfacePickup': (
        _SolveField('surface', 'Surface', 'int'),
        _SolveField('scale', 'ScaleFactor', 'float', 'SupportsScale'),
        _SolveField('offset', 'Offset', 'float', 'SupportsOffset'),
        _SolveField('column', 'Column', 'column', required=False),
    ),
    'FNumber': (
        _SolveField('f_number', 'FNumber', 'float'),
    ),
    'Position': (
        _SolveField('from_surface', 'FromSurface', 'int'),
        _SolveField('length', 'Length', 'float'),
    ),
    'ConfigPickup': (
        _SolveField('operand', 'Operand', 'int'),
        _SolveField('configuration', 'Configuration', 'int'),
        _SolveField('scale', 'ScaleFactor', 'float', 'SupportsScale'),
        _SolveField('offset', 'Offset', 'float', 'SupportsOffset'),
    ),
    'ThermalPickup': (
        _SolveField('configuration', 'Configuration', 'int'),
    ),
}


def _read_solve(cell) -> dict[str, object]:
    kind = str(cell.Solve)
    fields = _SOLVE_FIELDS.get(kind)

    if not fields:
        return {'type': kind}

    data = cell.GetSolveData()

    if data is None:
        return {'type': kind}

    body = getattr(data, '_S_' + kind)
    result: dict[str, object] = {'type': kind}

    for field in fields:
        if field.capability and not bool(getattr(body, field.capability)):
            continue

        if field.name == 'column' and bool(body.IsPickupFromCurrentColumn()):
            continue

        raw = getattr(body, field.source)

        if field.kind == 'int':
            result[field.name] = int(raw)
        elif field.kind == 'float':
            result[field.name] = float(raw)
        else:
            result[field.name] = str(raw)

    return result


def _solve_request(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError('solve must be an object with a type.')

    kind = value.get('type')
    fields = _SOLVE_FIELDS.get(kind) if isinstance(kind, str) else None

    if fields is None:
        choices = ', '.join(_SOLVE_TYPES)
        raise ValueError(f'solve.type must be one of: {choices}.')

    allowed = {field.name: field for field in fields}
    prepared: dict[str, object] = {'type': kind}

    for key, item in value.items():
        if key == 'type':
            continue

        field = allowed.get(key)

        if field is None:
            names = ', '.join(('type', *(field.name for field in fields)))
            raise ValueError(f'Unknown solve field {key!r}. Expected one of: {names}.')

        prepared[key] = _solve_field_value(field, item)

    for field in fields:
        if field.required and not field.capability and field.name not in prepared:
            raise ValueError(f'{field.name} is required for {kind}.')

    return prepared


def _solve_field_value(field: _SolveField, value: object) -> object:
    if field.kind == 'column':
        if not isinstance(value, str):
            raise ValueError('column must be a string.')

        return value

    if field.kind == 'int':
        return _whole_number(field.name, value)

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{field.name} must be a number.')

    return float(value)


def _apply_solve(cell, request: dict[str, object]) -> None:
    import ZOSAPI

    kind = str(request['type'])
    enum = getattr(ZOSAPI.Editors.SolveType, kind)

    if cell.IsSolveTypeSupported(enum) is False:
        choices = cell.GetAvailableSolveTypes()
        available = ', '.join(str(item) for item in choices) if choices else ''
        message = f'{kind} is not available for this cell.'

        if available:
            message = f'{message} Expected one of: {available}.'

        raise ValueError(message)

    if kind == 'Variable':
        if cell.MakeSolveVariable() is False:
            raise ValueError('Variable solve could not be applied.')

        return

    if kind == 'Fixed':
        if cell.MakeSolveFixed() is False:
            raise ValueError('Fixed solve could not be applied.')

        return

    data = cell.CreateSolveType(enum)
    _fill_solve(data, request)
    status = cell.SetSolveData(data)

    if str(status) != 'Success':
        raise ValueError(f'The solve could not be applied. {status}')


def _fill_solve(data, request: dict[str, object]) -> None:
    kind = str(request['type'])
    body = getattr(data, '_S_' + kind)

    for field in _SOLVE_FIELDS[kind]:
        if field.name not in request:
            if field.name == 'column':
                body.MakePickupFromCurrentColumn()

            continue

        if field.capability and not bool(getattr(body, field.capability)):
            raise ValueError(f'{field.name} is not used by this {kind} solve.')

        if field.kind == 'column':
            body.Column = _surface_column(request[field.name])

            continue

        setattr(body, field.source, request[field.name])

    for field in _SOLVE_FIELDS[kind]:
        if field.capability and field.name not in request and bool(getattr(body, field.capability)):
            raise ValueError(f'{field.name} is required for {kind}.')


def _surface_column(name: object):
    if not isinstance(name, str):
        raise ValueError('column must be a string.')

    import clr
    import System
    import ZOSAPI

    enum = ZOSAPI.Editors.LDE.SurfaceColumn
    clr_type = clr.GetClrType(enum)

    if not System.Enum.IsDefined(clr_type, name):
        raise ValueError(f'Unknown column {name!r}.')

    return getattr(enum, name)


def _cell_write(label: str, value: object) -> tuple[object, dict[str, object] | None]:
    if not isinstance(value, dict):
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError(f'{label} must be a number or a string.')

        return value, None

    if not value or not set(value) <= {'value', 'solve'}:
        raise ValueError(f'{label} accepts value, solve, or both.')

    cell_value = _UNSET

    if 'value' in value:
        item = value['value']

        if isinstance(item, bool) or not isinstance(item, (int, float, str)):
            raise ValueError(f'{label} value must be a number or a string.')

        cell_value = item

    solve = _solve_request(value['solve']) if 'solve' in value else None

    return cell_value, solve


def _whole_number(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be an integer.')

    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f'{name} must be an integer.')

    return int(value)
