"""Multi-Configuration Editor tools."""

import typing

import mcp.server.mcpserver

import zemaxmcp.server as mcp_server

__all__ = [
    'get_multi_configuration',
    'set_multi_configuration_rows',
]

# A cell solve is an object inside a column value, which is itself inside `values`.
_SolveValue = str | float | int | dict[str, str | float | int]
_CellValue = str | float | int | dict[str, _SolveValue]
_EditorValues = dict[str, str | float | bool | int | dict[str, _CellValue]]

@mcp_server.server.tool(
    description='Return the Multi-Configuration Editor, or one operand when `operand` is given.',
)
def get_multi_configuration(
    ctx: mcp.server.mcpserver.Context,
    operand: int | None = None,
) -> dict[str, object]:
    """
    Return the Multi-Configuration Editor for the lens open in the OpticStudio window.

    Pass ``operand`` to read one operand. Omit it to read the current configuration, every configuration column, and every operand.

    :param operand: Operand number. The first operand is 1. ``None`` reads the whole editor.
    :returns: Without ``operand``, ``current``, ``configurations``, and ``operands``. With ``operand``, that operand.

        * **current** -- Configuration shown in the Lens Data Editor. Present when ``operand`` is omitted.
        * **configurations** -- One entry per configuration column, in editor order. Present when ``operand`` is omitted.
        * **configurations[].number** -- 1-based configuration number.
        * **operands** -- One entry per operand, in editor order. Present when ``operand`` is omitted.
        * **number** -- Operand number. The first operand is 1. This member is read-only.
        * **active** -- True when the operand is active. This member is read-only.
        * **type** -- Operand type, such as ``THIC`` or ``GLSS``.
        * **parameters** -- Parameter columns used by ``type``. Empty when the type uses none.
        * **parameters[].column** -- ``Param1``, ``Param2``, or ``Param3``.
        * **parameters[].value** -- Integer stored in that column, such as a surface number.
        * **cells** -- One entry per configuration column.
        * **cells[].configuration** -- Configuration number.
        * **cells[].value** -- Cell value. A number, or a string when the cell stores text, such as a glass name.
        * **cells[].solve** -- Solve on that configuration cell. The same object as ``radius_solve`` returned by :meth:`get_lens_data`.
    :rtype: dict[str, object]
    :raises ValueError: ``operand`` is outside the editor.
    """

    return mcp_server.read(ctx, lambda session: session.multi_configuration(operand))


@mcp_server.server.tool(
    description=(
        'Change the Multi-Configuration Editor. '
        '`section` is `operand` or `configuration`. '
        '`action` is `change`, `add`, `remove`, or `make_current`. '
        '`make_current` selects the configuration shown in the Lens Data Editor. '
        '`values` uses the same fields as one operand returned by `get_multi_configuration`. '
        'A cell may be a value, or an object with `value` and `solve`. '
        '`type` sets the operand type before parameters and configuration cells.'
    ),
)
def set_multi_configuration_rows(
    ctx: mcp.server.mcpserver.Context,
    section: typing.Literal['operand', 'configuration'],
    action: typing.Literal['change', 'add', 'remove', 'make_current'],
    number: int,
    values: _EditorValues | None = None,
) -> dict[str, object]:
    """
    Change one Multi-Configuration Editor operand or configuration and return the editor.

    :param section: ``operand`` or ``configuration``.
    :param action: ``change``, ``add``, ``remove``, or ``make_current``. ``make_current`` selects the configuration shown in the Lens Data Editor.
    :param number: 1-based operand or configuration number. ``add`` inserts at this number, and following rows or columns move up. Pass ``number`` one past the last entry to append.
    :param values: Keys to write. For an operand, the fields are the same as those of one operand returned by :meth:`get_multi_configuration`. Omit ``values`` to insert a default operand or configuration, or to remove one. ``number`` and ``active`` are read-only. ``type`` is an operand type name, such as ``THIC``. ``parameters`` maps ``Param1``, ``Param2``, or ``Param3`` to an integer. ``cells`` maps a configuration number, such as ``"1"``, to a number, a string, or an object with ``value`` and ``solve``. ``type`` is applied before ``parameters`` and ``cells``. A configuration has no fields to change. ``add`` for a configuration accepts ``copy``: true copies the current configuration's cells. The last configuration cannot be removed.
    :returns: ``current``, ``configurations``, and ``operands`` after the change.
    :rtype: dict[str, object]
    :raises ValueError: The section, action, number, or values cannot be applied.
    """

    return mcp_server.read(
        ctx,
        lambda session: session.set_multi_configuration_rows(section, action, number, values),
    )
