"""System Explorer tools."""

import typing

import mcp.server.mcpserver

import zaymcp.server as mcp_server

__all__ = [
    'get_system_settings',
    'set_system_settings',
    'set_system_rows',
]

@mcp_server.server.tool(
    description='Return one group of settings from System Explorer.',
)
def get_system_settings(
    ctx: mcp.server.mcpserver.Context,
    section: typing.Literal[
        'units',
        'aperture',
        'fields',
        'wavelengths',
        'environment',
        'polarization',
        'ray_aiming',
    ],
) -> dict[str, object] | list[dict[str, object]]:
    """
    Return one group of System Explorer settings.

    :param section: ``units``, ``aperture``, ``fields``, ``wavelengths``, ``environment``, ``polarization``, or ``ray_aiming``.
    :returns: The selected group. ``wavelengths`` is a list of wavelengths in micrometers. The other groups are dictionaries.

        **units**

        * **lens_units** -- Millimeters, Centimeters, Inches, or Meters.
        * **source_unit_prefix** -- Prefix applied to source units, such as ``None`` or ``Milli``.
        * **source_units** -- Watts, Lumens, or Joules.
        * **analysis_unit_prefix** -- Prefix applied to analysis units.
        * **analysis_units** -- Irradiance unit, such as ``WattsPerMMSq``.
        * **afocal_mode_units** -- Angular unit used when afocal image space is enabled, such as ``Milliradians`` or ``Degrees``.
        * **mtf_units** -- ``CyclesPerMillimeter`` or ``CyclesPerMilliradian``.

        **aperture**

        * **aperture_type** -- ``EntrancePupilDiameter``, ``ImageSpaceFNum``, ``ObjectSpaceNA``, ``FloatByStopSize``, ``ParaxialWorkingFNum``, or ``ObjectConeAngle``.
        * **aperture_value** -- ``EntrancePupilDiameter`` is a diameter in lens units. ``ImageSpaceFNum`` and ``ParaxialWorkingFNum`` are dimensionless. ``ObjectSpaceNA`` is dimensionless. ``ObjectConeAngle`` is in degrees. ``FloatByStopSize`` takes the aperture from the stop surface semi-diameter.
        * **apodization_type** -- ``Uniform``, ``Gaussian``, or ``CosineCubed``.
        * **apodization_factor** -- Apodization factor. Meaningful when ``apodization_factor_is_used`` is true.
        * **apodization_factor_is_used** -- True when the apodization factor is used. This member is read-only.
        * **semi_diameter_margin** -- Length added to computed semi-diameters, in lens units.
        * **semi_diameter_margin_percent** -- Percent added to computed semi-diameters.
        * **global_coordinate_reference_surface** -- Surface number used as the global coordinate reference. 0 is the object surface.
        * **telecentric_object_space** -- True when object-space telecentricity is enabled.
        * **afocal_image_space** -- True when afocal image space is enabled.
        * **iterate_solves_when_updating** -- True when solves are iterated while the system updates.
        * **fast_semi_diameters** -- True when fast semi-diameter computation is enabled.
        * **check_grin_apertures** -- True when GRIN apertures are checked.

        **fields**

        * **type** -- ``Angle``, ``ObjectHeight``, ``ParaxialImageHeight``, ``RealImageHeight``, or ``TheodoliteAngle``.
        * **normalization** -- ``Radial`` or ``Rectangular``.
        * **points** -- One entry per field. ``x`` and ``y`` are degrees for ``Angle`` and ``TheodoliteAngle``, and lens units for the height types.
        * **points[].number** -- 1-based field number.
        * **points[].active** -- True when the field is active.
        * **points[].x** -- X field coordinate.
        * **points[].y** -- Y field coordinate.
        * **points[].weight** -- Relative field weight.
        * **points[].vdx** -- Vignetting decenter in X, as a fraction of the pupil.
        * **points[].vdy** -- Vignetting decenter in Y, as a fraction of the pupil.
        * **points[].vcx** -- Vignetting compression in X, as a fraction of the pupil.
        * **points[].vcy** -- Vignetting compression in Y, as a fraction of the pupil.
        * **points[].van** -- Vignetting angle, in degrees.
        * **points[].tan** -- Tangential angle, in degrees.
        * **points[].comment** -- Field comment. Empty when the field has no comment.
        * **points[].x_solve** -- Solve type for X, such as ``Fixed``.
        * **points[].y_solve** -- Solve type for Y, such as ``Fixed``.
        * **points[].ignore** -- True when the field is ignored.

        **wavelengths**

        * **number** -- 1-based wavelength number.
        * **active** -- True when the wavelength is active.
        * **wavelength** -- Wavelength in micrometers.
        * **weight** -- Relative wavelength weight.
        * **primary** -- True for the primary wavelength.

        **environment**

        * **temperature** -- Temperature in degrees Celsius.
        * **pressure** -- Pressure in atmospheres.
        * **adjust_index_to_environment** -- True when refractive indices are adjusted to the system temperature and pressure.

        **polarization**

        * **method** -- ``XAxisMethod``, ``YAxisMethod``, or ``ZAxisMethod``.
        * **unpolarized** -- True when the input beam is unpolarized.
        * **jx** -- Jones vector X component.
        * **jy** -- Jones vector Y component.
        * **x_phase** -- X phase, in degrees.
        * **y_phase** -- Y phase, in degrees.
        * **convert_thin_film_phase_to_ray_equivalent** -- True when thin-film phase is converted to a ray-equivalent angle.

        **ray_aiming**

        * **setting** -- ``Off``, ``Paraxial``, or ``Real``.
        * **method** -- ``Heuristic`` or ``Optimize``. Used when ``setting`` is ``Real``.
        * **use_ray_aiming_cache** -- True when the ray-aiming cache is used.
        * **use_robust_ray_aiming** -- True when robust ray aiming is used.
        * **scale_pupil_shift_factors_by_field** -- True when pupil-shift factors are scaled by field.
        * **automatically_calculate_pupil_shifts** -- True when pupil shifts are calculated automatically.
        * **use_enhanced_ray_aiming** -- True when enhanced ray aiming is used.
        * **use_advanced_convergence** -- True when advanced convergence is used.
        * **use_fallback_search_during_cache_setup** -- True when cache setup falls back to a search.
        * **pupil_shift_x** -- Pupil shift factor in X.
        * **pupil_shift_y** -- Pupil shift factor in Y.
        * **pupil_shift_z** -- Pupil shift factor in Z.
        * **pupil_compress_x** -- Pupil compression factor in X.
        * **pupil_compress_y** -- Pupil compression factor in Y.
        * **cache_setup_steps** -- Number of steps used to build the ray-aiming cache.
    :rtype: dict[str, object] | list[dict[str, object]]
    :raises ValueError: ``section`` is not a setting group.
    """

    return mcp_server.read(ctx, lambda session: session.system_data(section))


@mcp_server.server.tool(
    description=(
        'Change one group of settings in System Explorer. '
        'Fields in `values` are the same fields returned by `get_system_settings` for that group. '
        'Only keys in `values` are written. '
        'Field points and wavelengths are lists of rows. Change those with `set_system_rows`.'
    ),
)
def set_system_settings(
    ctx: mcp.server.mcpserver.Context,
    section: typing.Literal[
        'units',
        'aperture',
        'fields',
        'wavelengths',
        'environment',
        'polarization',
        'ray_aiming',
    ],
    values: dict[str, str | float | bool | int],
) -> dict[str, object] | list[dict[str, object]]:
    """
    Change keys in one System Explorer setting group and return the group.

    :param section: ``units``, ``aperture``, ``fields``, ``wavelengths``, ``environment``, ``polarization``, or ``ray_aiming``.
    :param values: Keys to change. The fields are the same as those returned by :meth:`get_system_settings` for ``section``. ``apodization_factor_is_used`` is read-only. ``points`` and ``wavelengths`` are lists of rows; change them with :meth:`set_system_rows`.
    :returns: The setting group after the change.
    :rtype: dict[str, object] | list[dict[str, object]]
    :raises ValueError: ``section`` is unknown, ``values`` is empty, or a key cannot be changed.
    """

    return mcp_server.read(ctx, lambda session: session.set_system_data(section, values))


@mcp_server.server.tool(
    description=(
        'Change one field point or wavelength in System Explorer. '
        '`action` is `change`, `add`, `remove`, or `make_primary`. '
        '`number` is the 1-based row. `add` appends a row and does not use `number`. '
        '`values` uses the same fields as one row returned by `get_system_settings`. '
        '`make_primary` selects the primary wavelength.'
    ),
)
def set_system_rows(
    ctx: mcp.server.mcpserver.Context,
    section: typing.Literal['fields', 'wavelengths'],
    action: typing.Literal['change', 'add', 'remove', 'make_primary'],
    number: int | None = None,
    values: dict[str, str | float | bool | int] | None = None,
) -> list[dict[str, object]]:
    """
    Change, add, or remove one field point or wavelength and return the rows.

    :param section: ``fields`` or ``wavelengths``.
    :param action: ``change``, ``add``, ``remove``, or ``make_primary``.
    :param number: 1-based row. Required for ``change``, ``remove``, and ``make_primary``. ``add`` appends a row.
    :param values: Keys to write. The fields are the same as those of one row returned by :meth:`get_system_settings`. Omit ``values`` for ``remove`` and ``make_primary``.

        **fields**

        ``add`` requires ``x``, ``y``, and ``weight``. ``x`` and ``y`` are degrees for ``Angle`` and ``TheodoliteAngle``, and lens units for the height types.

        * **x** -- X field coordinate.
        * **y** -- Y field coordinate.
        * **weight** -- Relative field weight.
        * **vdx** -- Vignetting decenter in X, as a fraction of the pupil.
        * **vdy** -- Vignetting decenter in Y, as a fraction of the pupil.
        * **vcx** -- Vignetting compression in X, as a fraction of the pupil.
        * **vcy** -- Vignetting compression in Y, as a fraction of the pupil.
        * **van** -- Vignetting angle, in degrees.
        * **tan** -- Tangential angle, in degrees.
        * **comment** -- Field comment.
        * **ignore** -- True when the field is ignored.

        ``number``, ``active``, ``x_solve``, and ``y_solve`` are read-only.

        **wavelengths**

        ``add`` requires ``wavelength`` and ``weight``. ``wavelength`` is in micrometers.

        * **wavelength** -- Wavelength in micrometers.
        * **weight** -- Relative wavelength weight.

        ``number``, ``active``, and ``primary`` are read-only. ``make_primary`` selects the primary wavelength.
    :returns: The rows after the change. For ``fields``, these are the field points.
    :rtype: list[dict[str, object]]
    :raises ValueError: ``section`` has no row list, or the action, number, or values cannot be applied.
    """

    return mcp_server.read(ctx, lambda session: session.set_system_rows(section, action, number, values))
