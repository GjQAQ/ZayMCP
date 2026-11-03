"""Local optimization tool."""

import typing

import mcp.server.mcpserver

import zaymcp.server as mcp_server
import zaymcp.zosapi.optimize.automatic_optimization.local_optimization as local_optimization

__all__ = [
    'run_local_optimization',
]

_Algorithm = typing.Literal['DampedLeastSquares', 'OrthogonalDescent']
_Cycles = typing.Literal[
    'Automatic',
    'Fixed_1_Cycle',
    'Fixed_5_Cycles',
    'Fixed_10_Cycles',
    'Fixed_50_Cycles',
]

if typing.get_args(_Algorithm) != local_optimization.ALGORITHMS:
    raise RuntimeError('Local optimization algorithms do not match the tool schema.')

if typing.get_args(_Cycles) != local_optimization.CYCLES:
    raise RuntimeError('Local optimization cycles do not match the tool schema.')


@mcp_server.server.tool(
    description=(
        'Run local optimization on the open lens and return the merit function before and after. '
        'The default algorithm is damped least squares, and the default cycles are automatic. '
        '`algorithm` is `DampedLeastSquares` or `OrthogonalDescent`. '
        '`cycles` is `Automatic`, `Fixed_1_Cycle`, `Fixed_5_Cycles`, `Fixed_10_Cycles`, or `Fixed_50_Cycles`.'
    ),
)
def run_local_optimization(
    ctx: mcp.server.mcpserver.Context,
    algorithm: _Algorithm = 'DampedLeastSquares',
    cycles: _Cycles = 'Automatic',
) -> dict[str, object]:
    """
    Run local optimization on the lens open in the OpticStudio window.

    The call waits until the run finishes. The core count stays at the value already set in the Optimize dialog.

    :param algorithm: ``DampedLeastSquares`` or ``OrthogonalDescent``.
    :param cycles: ``Automatic``, ``Fixed_1_Cycle``, ``Fixed_5_Cycles``, ``Fixed_10_Cycles``, or ``Fixed_50_Cycles``.
    :returns:
        * **algorithm** -- Algorithm that ran.
        * **cycles** -- Cycle count that ran.
        * **variables** -- Number of variables, as shown in the Optimize dialog.
        * **targets** -- Number of targets, as shown in the Optimize dialog.
        * **initial_merit** -- Merit function value before the run. ``None`` when OpticStudio does not return a finite value.
        * **merit** -- Merit function value after the run. ``None`` when OpticStudio does not return a finite value.
    :rtype: dict[str, object]
    :raises ValueError: The algorithm or cycles cannot be used, the lens has no variable or no target, or the run does not finish.
    """

    return mcp_server.read(
        ctx,
        lambda session: session.run_local_optimization(algorithm, cycles),
    )
