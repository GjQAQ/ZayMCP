"""Local optimization for the open lens."""

import math

from zaymcp.zosapi.errors import OpticStudioError
from zaymcp.zosapi.model.fields import text

__all__ = [
    'ALGORITHMS',
    'CYCLES',
]

#: Algorithms accepted by local optimization, in dialog order.
ALGORITHMS: tuple[str, ...] = (
    'DampedLeastSquares',
    'OrthogonalDescent',
)

#: Cycle counts accepted by local optimization. Infinite is omitted because the call waits until the run finishes.
CYCLES: tuple[str, ...] = (
    'Automatic',
    'Fixed_1_Cycle',
    'Fixed_5_Cycles',
    'Fixed_10_Cycles',
    'Fixed_50_Cycles',
)


def _choice(name: str, value: object, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in choices:
        allowed = ', '.join(choices)
        raise ValueError(f'{name} must be one of: {allowed}.')

    return value


def _finite(value: object) -> float | None:
    number = float(value)

    return number if math.isfinite(number) else None


def _close_optimization(tool) -> None:
    # The merit values are already copied. Closing the tool should not replace that result.
    try:
        tool.Close()
    except Exception:
        return


def _run_local_optimization(system, algorithm: str, cycles: str) -> dict[str, object]:
    # Open the dialog only after the arguments are known to be names it accepts.
    algorithm_name = _choice('algorithm', algorithm, ALGORITHMS)
    cycles_name = _choice('cycles', cycles, CYCLES)

    import ZOSAPI

    optimization = ZOSAPI.Tools.Optimization
    algorithm_value = getattr(optimization.OptimizationAlgorithm, algorithm_name)
    cycles_value = getattr(optimization.OptimizationCycles, cycles_name)

    try:
        tool = system.Tools.OpenLocalOptimization()
    except OpticStudioError:
        raise
    except Exception as exc:
        raise ValueError(f'Local optimization could not be opened. {exc}') from exc

    if tool is None:
        raise ValueError('Local optimization could not be opened.')

    try:
        tool.Algorithm = algorithm_value
        tool.Cycles = cycles_value
        variables = int(tool.Variables)
        targets = int(tool.Targets)
        initial_merit = _finite(tool.InitialMeritFunction)

        if variables < 1:
            raise ValueError('Local optimization needs at least one variable.')

        if targets < 1:
            raise ValueError('Local optimization needs at least one target.')

        try:
            completed = bool(tool.RunAndWaitForCompletion())
        except OpticStudioError:
            raise
        except Exception as exc:
            raise ValueError(f'Local optimization did not complete. {exc}') from exc

        if not completed:
            message = text(tool.ErrorMessage)

            if message:
                raise ValueError(f'Local optimization did not complete. {message}')

            raise ValueError('Local optimization did not complete.')

        return {
            'algorithm': algorithm_name,
            'cycles': cycles_name,
            'variables': variables,
            'targets': targets,
            'initial_merit': initial_merit,
            'merit': _finite(tool.CurrentMeritFunction),
        }
    finally:
        _close_optimization(tool)
