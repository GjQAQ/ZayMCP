"""Merit Function Editor tools."""

import typing

import mcp.server.mcpserver

import zaymcp.server as mcp_server

__all__ = [
    'get_merit_function',
    'set_merit_rows',
    'calculate_merit_function',
]

@mcp_server.server.tool(
    description='Return the Merit Function Editor operands, or one operand when `operand` is given.',
)
def get_merit_function(
    ctx: mcp.server.mcpserver.Context,
    operand: int | None = None,
) -> dict[str, object]:
    """
    Return the Merit Function Editor operands for the lens open in the OpticStudio window.

    Pass ``operand`` to read one operand. Omit it to read every operand.

    :param operand: Operand number. The first operand is 1. ``None`` reads every operand.
    :returns: Without ``operand``, ``operands``. With ``operand``, that operand.

        * **operands** -- One entry per operand, in editor order. Present when ``operand`` is omitted.
        * **number** -- Operand number. The first operand is 1. This member is read-only.
        * **active** -- True when the operand is active. This member is read-only.
        * **type** -- Operand type, such as ``EFFL``.
        * **parameters** -- Data columns used by ``type``. Empty when the type uses none.
        * **parameters[].column** -- Column name, such as ``Param1``.
        * **parameters[].header** -- Column title from the Merit Function Editor. This member is read-only.
        * **parameters[].value** -- Cell value. A number, or a string when the cell stores text.
        * **target** -- Target value.
        * **weight** -- Operand weight.
        * **value** -- Operand value currently shown in the editor. This member is read-only.
        * **contribution** -- Contribution of this operand to the merit function, as currently shown. This member is read-only.
        * **comment** -- Operand comment. Empty when the operand has no comment.
    :rtype: dict[str, object]
    :raises ValueError: ``operand`` is outside the editor.
    """

    return mcp_server.read(ctx, lambda session: session.merit_function(operand))


@mcp_server.server.tool(
    description=(
        'Change, insert, or remove one operand in the Merit Function Editor. '
        '`action` is `change`, `add`, or `remove`. '
        '`number` is the 1-based operand. '
        '`add` inserts an operand at `number`. '
        '`values` uses the same fields as one operand returned by `get_merit_function`. '
        '`type` sets the operand type. '
        '`parameters` maps column names such as `Param1` to new values. '
        'When both are set, the type changes first.'
    ),
)
def set_merit_rows(
    ctx: mcp.server.mcpserver.Context,
    action: typing.Literal['change', 'add', 'remove'],
    number: int,
    values: dict[str, str | float | bool | int | dict[str, str | float | int]] | None = None,
) -> dict[str, object]:
    """
    Change, insert, or remove one Merit Function Editor operand and return the editor.

    :param action: ``change``, ``add``, or ``remove``.
    :param number: Operand number. The first operand is 1. ``add`` inserts at this number, and following operands move up. The inserted operand keeps the editor default until ``values`` sets ``type``. Pass ``number`` one past the last operand to append.
    :param values: Keys to write. The fields are the same as those of one operand returned by :meth:`get_merit_function`. Omit ``values`` to insert a default operand or to remove an operand. ``number``, ``active``, ``value``, and ``contribution`` are read-only. ``type`` is an operand type name, such as ``EFFL``. ``parameters`` maps column names such as ``Param1`` to a number or a string; only listed columns are written, and ``header`` is read-only. ``type`` is applied before ``parameters``.
    :returns: The operands after the change.
    :rtype: dict[str, object]
    :raises ValueError: The action, number, or values cannot be applied.
    """

    return mcp_server.read(ctx, lambda session: session.set_merit_rows(action, number, values))


@mcp_server.server.tool(
    description=(
        'Calculate the merit function for the open lens. '
        'Returns the merit value and the operands with updated values and contributions.'
    ),
)
def calculate_merit_function(ctx: mcp.server.mcpserver.Context) -> dict[str, object]:
    """
    Calculate the merit function and return its value and the updated operands.

    :returns:
        * **merit** -- Merit function value. ``None`` when OpticStudio does not return a finite value.
        * **operands** -- One entry per operand, in editor order, after the calculation. The fields of each operand are the same as those returned by :meth:`get_merit_function`. ``value`` and ``contribution`` are the calculated numbers.
    :rtype: dict[str, object]
    :raises ValueError: The merit function cannot be calculated.
    """

    return mcp_server.read(ctx, lambda session: session.calculate_merit_function())
