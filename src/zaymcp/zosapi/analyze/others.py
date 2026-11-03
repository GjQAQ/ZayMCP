"""First-order values read through merit-function operands."""

import math

from zaymcp.zosapi.model.fields import text

# Name, operand, and the two integer arguments. Wave 0 selects the primary wavelength.
# TOTR starts at surface 1; a second integer of 0 ends at the image surface.
_FIRST_ORDER: tuple[tuple[str, str, int, int], ...] = (
    ('effective_focal_length', 'EFFL', 0, 0),
    ('entrance_pupil_diameter', 'EPDI', 0, 0),
    ('image_space_f_number', 'ISFN', 0, 0),
    ('working_f_number', 'WFNO', 0, 0),
    ('total_length', 'TOTR', 1, 0),
)


def _read_first_order(system) -> dict[str, float | str | None]:
    # Update first so the operands see the latest solves.
    status = text(system.UpdateStatus())
    editor = system.MFE

    import ZOSAPI

    operand = ZOSAPI.Editors.MFE.MeritOperandType
    values: dict[str, float | str | None] = {}

    for name, kind, surf, wave in _FIRST_ORDER:
        raw = editor.GetOperandValue(getattr(operand, kind), surf, wave, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        number = float(raw)
        values[name] = number if math.isfinite(number) else None

    values['status'] = status

    return values
