"""System Explorer setting groups."""

from zaymcp.zosapi.model.fields import Attribute, Listing, Rows, Section, text

__all__ = [
    'SYSTEM',
    'row_editor',
    'setting_group',
]

def setting_group(name: str) -> Section | Listing:
    """
    Return one System Explorer setting group.

    :param str name: ``units``, ``aperture``, ``fields``, ``wavelengths``, ``environment``, ``polarization``, or ``ray_aiming``.
    :returns: The group.
    :rtype: Section | Listing
    :raises ValueError: ``name`` is not a setting group.
    """

    try:
        return SYSTEM[name]
    except KeyError:
        choices = ', '.join(SYSTEM)
        raise ValueError(f'Unknown system setting group {name!r}. Expected one of: {choices}.') from None


def row_editor(name: str) -> tuple[str, Rows]:
    """
    Return the SystemData property and row list for one editable group.

    :param str name: ``fields`` or ``wavelengths``.
    :returns: The property name on SystemData, and the rows to edit.
    :rtype: tuple[str, Rows]
    :raises ValueError: ``name`` is not a setting group, or that group has no row list.
    """

    group = setting_group(name)
    editor = _row_editor(group)

    if editor is None:
        choices = ', '.join(label for label, item in SYSTEM.items() if _row_editor(item) is not None)
        raise ValueError(f'{name} has no row list. Expected one of: {choices}.')

    return editor


def _row_editor(group: Section | Listing) -> tuple[str, Rows] | None:
    # A listing is the row list. A section contributes its one editable collection.
    if isinstance(group, Listing) and group.rows.add is not None:
        return group.source, group.rows

    if isinstance(group, Section) and len(group.rows) == 1 and group.rows[0][1].add is not None:
        return group.source, group.rows[0][1]

    return None


#: System Explorer setting groups, keyed by the name passed to OpticStudioSession.system_data.
SYSTEM: dict[str, Section | Listing] = {
    'units': Section(
        'Units',
        (
            Attribute('lens_units', 'LensUnits', str, enumeration='ZemaxSystemUnits'),
            Attribute('source_unit_prefix', 'SourceUnitPrefix', str, enumeration='ZemaxUnitPrefix'),
            Attribute('source_units', 'SourceUnits', str, enumeration='ZemaxSourceUnits'),
            Attribute('analysis_unit_prefix', 'AnalysisUnitPrefix', str, enumeration='ZemaxUnitPrefix'),
            Attribute('analysis_units', 'AnalysisUnits', str, enumeration='ZemaxAnalysisUnits'),
            Attribute('afocal_mode_units', 'AfocalModeUnits', str, enumeration='ZemaxAfocalModeUnits'),
            Attribute('mtf_units', 'MTFUnits', str, enumeration='ZemaxMTFUnits'),
        ),
    ),
    'aperture': Section(
        'Aperture',
        (
            Attribute('aperture_type', 'ApertureType', str, enumeration='ZemaxApertureType'),
            Attribute('aperture_value', 'ApertureValue', float),
            Attribute('apodization_type', 'ApodizationType', str, enumeration='ZemaxApodizationType'),
            Attribute('apodization_factor', 'ApodizationFactor', float),
            Attribute('apodization_factor_is_used', 'ApodizationFactorIsUsed', bool, writable=False),
            Attribute('semi_diameter_margin', 'SemiDiameterMargin', float),
            Attribute('semi_diameter_margin_percent', 'SemiDiameterMarginPct', float),
            Attribute('global_coordinate_reference_surface', ('GCRS', 'GetSelectedSurface'), int, call=True),
            Attribute('telecentric_object_space', 'TelecentricObjectSpace', bool),
            Attribute('afocal_image_space', 'AFocalImageSpace', bool),
            Attribute('iterate_solves_when_updating', 'IterateSolvesWhenUpdating', bool),
            Attribute('fast_semi_diameters', 'FastSemiDiameters', bool),
            Attribute('check_grin_apertures', 'CheckGRINApertures', bool),
        ),
    ),
    'fields': Section(
        'Fields',
        (
            Attribute('type', 'GetFieldType', str, call=True, enumeration='FieldType'),
            Attribute('normalization', 'Normalization', str, enumeration='FieldNormalizationType'),
        ),
        (
            (
                'points',
                Rows(
                    'NumberOfFields',
                    'GetField',
                    (
                        Attribute('number', 'FieldNumber', int, writable=False),
                        Attribute('active', 'IsActive', bool, writable=False),
                        Attribute('x', 'X', float),
                        Attribute('y', 'Y', float),
                        Attribute('weight', 'Weight', float),
                        Attribute('vdx', 'VDX', float),
                        Attribute('vdy', 'VDY', float),
                        Attribute('vcx', 'VCX', float),
                        Attribute('vcy', 'VCY', float),
                        Attribute('van', 'VAN', float),
                        Attribute('tan', 'TAN', float),
                        Attribute('comment', 'Comment', text),
                        Attribute('x_solve', 'XSolve', str, writable=False),
                        Attribute('y_solve', 'YSolve', str, writable=False),
                        Attribute('ignore', 'Ignore', bool),
                    ),
                    'AddField',
                    ('x', 'y', 'weight'),
                    'RemoveField',
                ),
            ),
        ),
    ),
    'wavelengths': Listing(
        'Wavelengths',
        Rows(
            'NumberOfWavelengths',
            'GetWavelength',
            (
                Attribute('number', 'WavelengthNumber', int, writable=False),
                Attribute('active', 'IsActive', bool, writable=False),
                Attribute('wavelength', 'Wavelength', float),
                Attribute('weight', 'Weight', float),
                Attribute('primary', 'IsPrimary', bool, writable=False),
            ),
            'AddWavelength',
            ('wavelength', 'weight'),
            'RemoveWavelength',
            'MakePrimary',
        ),
    ),
    'environment': Section(
        'Environment',
        (
            Attribute('temperature', 'Temperature', float),
            Attribute('pressure', 'Pressure', float),
            Attribute('adjust_index_to_environment', 'AdjustIndexToEnvironment', bool),
        ),
    ),
    'polarization': Section(
        'Polarization',
        (
            Attribute('method', 'Method', str, enumeration='PolarizationMethod'),
            Attribute('unpolarized', 'Unpolarized', bool),
            Attribute('jx', 'Jx', float),
            Attribute('jy', 'Jy', float),
            Attribute('x_phase', 'XPhase', float),
            Attribute('y_phase', 'YPhase', float),
            Attribute('convert_thin_film_phase_to_ray_equivalent', 'ConvertThinFilmPhaseToRayEquivalent', bool),
        ),
    ),
    'ray_aiming': Section(
        'RayAiming',
        (
            Attribute('setting', 'RayAiming', str, enumeration='RayAimingMethod'),
            Attribute('method', 'Method', str, enumeration='RayAimingType'),
            Attribute('use_ray_aiming_cache', 'UseRayAimingCache', bool),
            Attribute('use_robust_ray_aiming', 'UseRobustRayAiming', bool),
            Attribute('scale_pupil_shift_factors_by_field', 'ScalePupilShiftFactorsByField', bool),
            Attribute('automatically_calculate_pupil_shifts', 'AutomaticallyCalculatePupilShiftsIsChecked', bool),
            Attribute('use_enhanced_ray_aiming', 'UseEnhancedRayAiming', bool),
            Attribute('use_advanced_convergence', 'UseAdvancedConvergence', bool),
            Attribute('use_fallback_search_during_cache_setup', 'UseFallBackSearchDuringCacheSetup', bool),
            Attribute('pupil_shift_x', 'PupilShiftX', float),
            Attribute('pupil_shift_y', 'PupilShiftY', float),
            Attribute('pupil_shift_z', 'PupilShiftZ', float),
            Attribute('pupil_compress_x', 'PupilCompressX', float),
            Attribute('pupil_compress_y', 'PupilCompressY', float),
            Attribute('cache_setup_steps', 'NumStepsCacheSetup', int),
        ),
    ),
}
