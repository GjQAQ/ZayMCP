"""Optimization Wizard controls."""

import dataclasses

from zemaxmcp.zosapi.errors import OpticStudioError
from zemaxmcp.zosapi.optimize.automatic_optimization.merit_function import MERIT

__all__ = [
    'SETTING_NAMES',
]

@dataclasses.dataclass(frozen=True)
class _WizardSetting:
    """One Optimization Wizard control."""

    #: Key accepted in ``values`` and returned in ``settings``.
    name: str
    #: ``bool``, ``int``, ``float``, ``choice``, ``arms``, or ``pupil``.
    kind: str
    #: Property name on ``ISEQOptimizationWizard2``. Empty when the control writes more than one property.
    source: str
    #: ZOS-API enumeration type in ``ZOSAPI.Wizards``. Empty when ``kind`` is not ``choice``.
    enumeration: str = ''
    #: Accepted names or arm counts.
    choices: tuple[str, ...] = ()
    #: Smallest accepted integer. ``None`` when the control is not an integer with a minimum.
    minimum: int | None = None


#: Optimization Wizard controls, in dialog order.
_WIZARD_SETTINGS: tuple[_WizardSetting, ...] = (
    _WizardSetting('criterion', 'choice', 'Criterion', 'CriterionTypes', ('Wavefront', 'Contrast', 'Spot', 'Angular')),
    _WizardSetting('type', 'choice', 'Type', 'OptimizationTypes', ('RMS', 'PTV')),
    _WizardSetting('reference', 'choice', 'Reference', 'ReferenceTypes', ('Centroid', 'ChiefRay', 'Unreferenced')),
    _WizardSetting('spatial_frequency', 'float', 'SpatialFrequency'),
    _WizardSetting('xs_weight', 'float', 'XSWeight'),
    _WizardSetting('yt_weight', 'float', 'YTWeight'),
    _WizardSetting('pupil_integration', 'pupil', '', choices=('GaussianQuadrature', 'RectangularArray')),
    _WizardSetting('rings', 'int', 'Rings', minimum=1),
    _WizardSetting('arms', 'arms', 'Arms', choices=('6', '8', '10', '12')),
    _WizardSetting('obscuration', 'float', 'Obscuration'),
    _WizardSetting('grid_size', 'int', 'GridSizeNxN', minimum=1),
    _WizardSetting('delete_vignetted', 'bool', 'DeleteVignetted'),
    _WizardSetting('use_glass_boundaries', 'bool', 'UseGlassBoundaryValues'),
    _WizardSetting('glass_min', 'float', 'GlassMin'),
    _WizardSetting('glass_max', 'float', 'GlassMax'),
    _WizardSetting('glass_edge', 'float', 'GlassEdgeThickness'),
    _WizardSetting('use_air_boundaries', 'bool', 'UseAirBoundaryValues'),
    _WizardSetting('air_min', 'float', 'AirMin'),
    _WizardSetting('air_max', 'float', 'AirMax'),
    _WizardSetting('air_edge', 'float', 'AirEdgeThickness'),
    _WizardSetting('start_at', 'int', 'StartAt', minimum=1),
    _WizardSetting('overall_weight', 'float', 'OverallWeight'),
    _WizardSetting('use_all_configurations', 'bool', 'UseAllConfigurations'),
    _WizardSetting('configuration', 'int', 'ConfigurationNumber', minimum=1),
    _WizardSetting('use_all_fields', 'bool', 'UseAllFields'),
    _WizardSetting('field', 'int', 'FieldNumber', minimum=1),
    _WizardSetting('assume_axial_symmetry', 'bool', 'AssumeAxialSymmetry'),
    _WizardSetting('ignore_lateral_color', 'bool', 'IgnoreLateralColor'),
    _WizardSetting('add_favorite_operands', 'bool', 'AddFavoriteOperands'),
    _WizardSetting('optimize_for_best_nominal_performance', 'bool', 'OptimizeForBestNominalPerformance'),
    _WizardSetting('optimize_for_manufacturing_yield', 'bool', 'OptimizeForManufacturingYield'),
    _WizardSetting('manufacturing_yield_weight', 'float', 'ManufacturingYieldWeight'),
    _WizardSetting('use_maximum_distortion', 'bool', 'UseMaximumDistortion'),
    _WizardSetting('maximum_distortion', 'float', 'MaxDistortionPct'),
)

_WIZARD_BY_NAME: dict[str, _WizardSetting] = {item.name: item for item in _WIZARD_SETTINGS}

# A thickness or a row number turns on the checkbox that makes it take effect.
_WIZARD_IMPLIED: tuple[tuple[tuple[str, ...], str, object], ...] = (
    (('glass_min', 'glass_max', 'glass_edge'), 'use_glass_boundaries', True),
    (('air_min', 'air_max', 'air_edge'), 'use_air_boundaries', True),
    (('configuration',), 'use_all_configurations', False),
    (('field',), 'use_all_fields', False),
)


def _wizard_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be an integer.')

    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f'{name} must be an integer.')

    return int(value)


def _wizard_value(setting: _WizardSetting, value: object) -> object:
    if setting.kind == 'bool':
        if not isinstance(value, bool):
            raise ValueError(f'{setting.name} must be a boolean.')

        return value

    if setting.kind == 'float':
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{setting.name} must be a number.')

        return float(value)

    if setting.kind in ('int', 'arms'):
        number = _wizard_integer(setting.name, value)

        if setting.kind == 'arms' and str(number) not in setting.choices:
            choices = ', '.join(setting.choices)
            raise ValueError(f'{setting.name} must be one of: {choices}.')

        if setting.minimum is not None and number < setting.minimum:
            raise ValueError(f'{setting.name} must be at least {setting.minimum}.')

        return number

    if not isinstance(value, str) or value not in setting.choices:
        choices = ', '.join(setting.choices)
        raise ValueError(f'{setting.name} must be one of: {choices}.')

    return value


def _wizard_assignments(values: object) -> list[tuple[str, object]]:
    if values is None:
        values = {}

    if not isinstance(values, dict):
        raise ValueError('values must be the wizard settings to change.')

    prepared = []
    seen = set()

    for key, value in values.items():
        setting = _WIZARD_BY_NAME.get(key)

        if setting is None:
            allowed = ', '.join(_WIZARD_BY_NAME)
            raise ValueError(f'Unknown setting {key!r}. Expected one of: {allowed}.')

        prepared.append((key, _wizard_value(setting, value)))
        seen.add(key)

    for sources, flag, implied in _WIZARD_IMPLIED:
        if flag in seen or not any(name in seen for name in sources):
            continue

        prepared.append((flag, implied))

    return prepared


def _assign_wizard(wizard, assignments: list[tuple[str, object]]) -> None:
    import ZOSAPI

    wizards = ZOSAPI.Wizards

    for name, value in assignments:
        setting = _WIZARD_BY_NAME[name]

        if setting.kind == 'pupil':
            wizard.UseGaussianQuadrature = value == 'GaussianQuadrature'
            wizard.UseRectangularArray = value == 'RectangularArray'

            continue

        if setting.kind == 'arms':
            wizard.Arms = getattr(wizards.PupilArmsCount, f'Arms_{value}')

            continue

        if setting.kind == 'choice':
            enumeration = getattr(wizards, setting.enumeration)
            setattr(wizard, setting.source, getattr(enumeration, value))

            continue

        setattr(wizard, setting.source, value)


def _wizard_pupil(wizard) -> str:
    gaussian = bool(wizard.UseGaussianQuadrature)
    rectangular = bool(wizard.UseRectangularArray)

    if rectangular and not gaussian:
        return 'RectangularArray'

    return 'GaussianQuadrature'


def _wizard_arms(wizard) -> int:
    name = str(wizard.Arms)
    number = name.removeprefix('Arms_')

    if number.isdigit():
        return int(number)

    raise ValueError(f'The Optimization Wizard returned an unknown arms value {name!r}.')


def _wizard_settings(wizard) -> dict[str, object]:
    settings = {}

    for setting in _WIZARD_SETTINGS:
        if setting.kind == 'pupil':
            settings[setting.name] = _wizard_pupil(wizard)

            continue

        if setting.kind == 'arms':
            settings[setting.name] = _wizard_arms(wizard)

            continue

        raw = getattr(wizard, setting.source)

        if setting.kind == 'bool':
            settings[setting.name] = bool(raw)
        elif setting.kind == 'int':
            settings[setting.name] = int(raw)
        elif setting.kind == 'float':
            settings[setting.name] = float(raw)
        else:
            settings[setting.name] = str(raw)

    return settings


def _apply_optimization_wizard(editor, values: dict[str, object] | None) -> dict[str, object]:
    assignments = _wizard_assignments(values)

    # A failed wizard leaves the Interactive Extension session open, so this raises ValueError.
    try:
        wizard = editor.SEQOptimizationWizard2

        if wizard is None:
            raise ValueError('The Optimization Wizard is not available.')

        # Reset is the wizard Reset button. Assignments then replace individual defaults.
        wizard.ResetSettings()
        _assign_wizard(wizard, assignments)
        # Apply writes the merit function, as the Optimization Wizard OK button does.
        wizard.Apply()
        settings = _wizard_settings(wizard)
    except OpticStudioError:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f'The Optimization Wizard could not be applied. {exc}') from exc

    return {
        'settings': settings,
        'operands': MERIT.read(editor)['operands'],
    }


#: Optimization Wizard control names, in dialog order.
SETTING_NAMES: tuple[str, ...] = tuple(item.name for item in _WIZARD_SETTINGS)
