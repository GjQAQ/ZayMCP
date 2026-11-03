"""Single Ray Trace analysis window."""

import os
import tempfile

from zaymcp.zosapi.model.fields import text

#: Table formats in the Single Ray Trace window.
_RAY_TRACE_TYPES: tuple[str, ...] = (
    'DirectionCosines',
    'TangentAngle',
    'YmUmYcUc',
)


def _ray_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a number.')

    return float(value)


def _ray_trace_request(
    wavelength: object,
    hx: object,
    hy: object,
    px: object,
    py: object,
    trace_type: object,
) -> dict[str, object]:
    if isinstance(wavelength, bool) or not isinstance(wavelength, int) or wavelength < 1:
        raise ValueError('wavelength must be an integer of at least 1.')

    if not isinstance(trace_type, str) or trace_type not in _RAY_TRACE_TYPES:
        choices = ', '.join(_RAY_TRACE_TYPES)
        raise ValueError(f'trace_type must be one of: {choices}.')

    return {
        'wavelength': wavelength,
        'hx': _ray_number('hx', hx),
        'hy': _ray_number('hy', hy),
        'px': _ray_number('px', px),
        'py': _ray_number('py', py),
        'type': trace_type,
    }


def _raise_analysis_message(message, action: str) -> None:
    if message is None or str(message.ErrorCode) == 'Success':
        return

    detail = text(message.Text)

    if detail:
        raise ValueError(f'{action} failed. {detail}')

    raise ValueError(f'{action} failed.')


def _analysis_text(results) -> str:
    handle = tempfile.NamedTemporaryFile(prefix='zaymcp-ray-', suffix='.txt', delete=False)
    handle.close()

    try:
        written = results.GetTextFile(handle.name)

        if written is False:
            raise ValueError('The Single Ray Trace table could not be read.')

        with open(handle.name, 'rb') as source:
            raw = source.read()
    finally:
        os.remove(handle.name)

    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        return raw.decode('utf-16')

    return raw.decode('utf-8', errors='replace')


def _ray_values(tokens: list[str]) -> list[object] | None:
    values = []

    for token in tokens:
        if token == '-':
            values.append(None)

            continue

        try:
            values.append(float(token))
        except ValueError:
            return None

    return values


def _ray_trace_table(page: str) -> tuple[list[str], list[dict[str, object]], str]:
    lines = page.splitlines()
    header_index = None

    for index, line in enumerate(lines):
        if line.strip().startswith('Surf'):
            header_index = index

            break

    if header_index is None:
        raise ValueError('The Single Ray Trace table was not found.')

    columns = lines[header_index].split()[1:]
    surfaces = []
    message = ''

    for line in lines[header_index + 1:]:
        if not line.strip():
            continue

        parts = line.split()
        values = _ray_values(parts[1:])

        if values is None:
            message = line.strip()

            break

        while len(values) < len(columns):
            values.append(None)

        surfaces.append({
            'surface': parts[0],
            'values': values,
        })

    return columns, surfaces, message


def _close_analysis(analysis) -> None:
    # The table is already copied. Closing the window should not replace that result.
    try:
        analysis.Close()
    except Exception:
        return


def _collect_ray_trace(analysis, settings, request: dict[str, object]) -> dict[str, object]:
    import ZOSAPI

    # UseGlobal makes Hx and Hy the field coordinates typed in the Single Ray Trace settings.
    settings.UseGlobal = True
    settings.Hx = request['hx']
    settings.Hy = request['hy']
    settings.Px = request['px']
    settings.Py = request['py']
    settings.Type = getattr(ZOSAPI.Analysis.Settings.Aberrations.RayTraceType, request['type'])
    _raise_analysis_message(settings.Wavelength.SetWavelengthNumber(request['wavelength']), 'Single Ray Trace')
    _raise_analysis_message(analysis.ApplyAndWaitForCompletion(), 'Single Ray Trace')
    columns, surfaces, message = _ray_trace_table(_analysis_text(analysis.GetResults()))

    return {
        'wavelength': request['wavelength'],
        'hx': request['hx'],
        'hy': request['hy'],
        'px': request['px'],
        'py': request['py'],
        'type': request['type'],
        'columns': columns,
        'surfaces': surfaces,
        'message': message,
    }


def _single_ray_trace(system, wavelength, hx, hy, px, py, trace_type: str) -> dict[str, object]:
    request = _ray_trace_request(wavelength, hx, hy, px, py, trace_type)

    import ZOSAPI

    analysis = system.Analyses.New_Analysis_SettingsFirst(ZOSAPI.Analysis.AnalysisIDM.RayTrace)

    if analysis is None:
        raise ValueError('Single Ray Trace could not be opened.')

    try:
        settings = ZOSAPI.Analysis.Settings.Aberrations.IAS_RayTrace(analysis.GetSettings())

        return _collect_ray_trace(analysis, settings, request)
    finally:
        _close_analysis(analysis)
