"""
Stdio MCP server.
"""

import contextlib
import typing

import mcp.server
import mcp.server.mcpserver
import mcp.server.mcpserver.exceptions
import pydantic

import zemaxmcp.opticstudio

__all__ = [
    'SERVER_NAME',
    'create_server',
    'main',
]

#: Name announced to an MCP host.
SERVER_NAME: str = "ZemaxMCP"


class OpticStudioConnection:
    """Keep one Interactive Extension session for this server process."""

    def __init__(self) -> None:
        #: The shared OpticStudio session. ``None`` before the first tool call and after a failed call.
        self.session: zemaxmcp.opticstudio.OpticStudioSession | None = None

    def open(self) -> zemaxmcp.opticstudio.OpticStudioSession:
        """
        Return the shared session, connecting on first use.

        :returns: The Interactive Extension session.
        :rtype: zemaxmcp.opticstudio.OpticStudioSession
        :raises zemaxmcp.opticstudio.OpticStudioError: OpticStudio cannot be connected.
        """

        if self.session is None:
            self.session = zemaxmcp.opticstudio.OpticStudioSession()

        return self.session

    def close(self) -> None:
        """Disconnect the shared session.

        Calling this again does nothing.
        """

        session = self.session
        self.session = None

        if session is not None:
            session.close()


@contextlib.asynccontextmanager
async def lifespan(server: mcp.server.MCPServer):
    """
    Keep one OpticStudio connection for the life of this server process.

    :param mcp.server.MCPServer server: The server being started.
    :returns: The connection yielded to each request.
    """

    # Close the OpticStudio connection when the host stops this process.
    connection = OpticStudioConnection()

    try:
        yield connection
    finally:
        connection.close()


class OptimizationWizardSettings(typing.TypedDict, total=False):
    """Optimization Wizard controls. Omit a property to keep the dialog default."""

    __pydantic_config__ = pydantic.ConfigDict(extra='forbid')

    criterion: typing.Annotated[
        typing.Literal['Wavefront', 'Contrast', 'Spot', 'Angular'],
        pydantic.Field(description='Wavefront, Contrast, Spot for spot radius, or Angular for angular radius.'),
    ]
    type: typing.Annotated[
        typing.Literal['RMS', 'PTV'],
        pydantic.Field(description='RMS or PTV.'),
    ]
    reference: typing.Annotated[
        typing.Literal['Centroid', 'ChiefRay', 'Unreferenced'],
        pydantic.Field(description='Centroid, ChiefRay, or Unreferenced.'),
    ]

    spatial_frequency: typing.Annotated[
        float,
        pydantic.Field(description='Spatial frequency used when criterion is Contrast. The unit follows the lens MTF units.'),
    ]
    xs_weight: typing.Annotated[float, pydantic.Field(description='XS contrast weight.')]
    yt_weight: typing.Annotated[float, pydantic.Field(description='YT contrast weight.')]

    pupil_integration: typing.Annotated[
        typing.Literal['GaussianQuadrature', 'RectangularArray'],
        pydantic.Field(description='Pupil sampling. GaussianQuadrature uses rings and arms. RectangularArray uses grid_size. Setting one turns the other off.'),
    ]
    rings: typing.Annotated[
        int,
        pydantic.Field(ge=1, description='Ring count for Gaussian quadrature. An integer of at least 1.'),
    ]
    arms: typing.Annotated[
        typing.Literal[6, 8, 10, 12],
        pydantic.Field(description='Arm count for Gaussian quadrature: 6, 8, 10, or 12.'),
    ]
    obscuration: typing.Annotated[
        float,
        pydantic.Field(description='Pupil obscuration for Gaussian quadrature, as shown in the wizard.'),
    ]
    grid_size: typing.Annotated[
        int,
        pydantic.Field(ge=1, description='Points along one side of the rectangular sampling grid. An integer of at least 1.'),
    ]
    delete_vignetted: typing.Annotated[bool, pydantic.Field(description='True when vignetted rays are deleted.')]

    use_glass_boundaries: typing.Annotated[bool, pydantic.Field(description='True when glass boundary operands are added.')]
    glass_min: typing.Annotated[
        float,
        pydantic.Field(description='Minimum glass thickness, in lens units. Turns use_glass_boundaries on when that property is omitted.'),
    ]
    glass_max: typing.Annotated[
        float,
        pydantic.Field(description='Maximum glass thickness, in lens units. Turns use_glass_boundaries on when that property is omitted.'),
    ]
    glass_edge: typing.Annotated[
        float,
        pydantic.Field(description='Minimum glass edge thickness, in lens units. Turns use_glass_boundaries on when that property is omitted.'),
    ]

    use_air_boundaries: typing.Annotated[bool, pydantic.Field(description='True when air boundary operands are added.')]
    air_min: typing.Annotated[
        float,
        pydantic.Field(description='Minimum air thickness, in lens units. Turns use_air_boundaries on when that property is omitted.'),
    ]
    air_max: typing.Annotated[
        float,
        pydantic.Field(description='Maximum air thickness, in lens units. Turns use_air_boundaries on when that property is omitted.'),
    ]
    air_edge: typing.Annotated[
        float,
        pydantic.Field(description='Minimum air edge thickness, in lens units. Turns use_air_boundaries on when that property is omitted.'),
    ]

    start_at: typing.Annotated[
        int,
        pydantic.Field(ge=1, description='1-based operand row where the new operands begin. Operands from this row through the end are replaced.'),
    ]
    overall_weight: typing.Annotated[float, pydantic.Field(description='Weight applied to the generated operands.')]

    use_all_configurations: typing.Annotated[bool, pydantic.Field(description='True when operands are built for every configuration.')]
    configuration: typing.Annotated[
        int,
        pydantic.Field(ge=1, description='1-based configuration number. Turns use_all_configurations off when that property is omitted.'),
    ]

    use_all_fields: typing.Annotated[bool, pydantic.Field(description='True when operands are built for every field.')]
    field: typing.Annotated[
        int,
        pydantic.Field(ge=1, description='1-based field number. Turns use_all_fields off when that property is omitted.'),
    ]

    assume_axial_symmetry: typing.Annotated[bool, pydantic.Field(description='True when the wizard assumes axial symmetry.')]
    ignore_lateral_color: typing.Annotated[bool, pydantic.Field(description='True when lateral color is ignored.')]
    add_favorite_operands: typing.Annotated[bool, pydantic.Field(description='True when favorite operands are added.')]

    optimize_for_best_nominal_performance: typing.Annotated[
        bool,
        pydantic.Field(description='True when the wizard optimizes the nominal design.'),
    ]
    optimize_for_manufacturing_yield: typing.Annotated[
        bool,
        pydantic.Field(description='True when manufacturing yield is included.'),
    ]
    manufacturing_yield_weight: typing.Annotated[float, pydantic.Field(description='Weight of the manufacturing-yield target.')]
    use_maximum_distortion: typing.Annotated[bool, pydantic.Field(description='True when distortion is limited.')]
    maximum_distortion: typing.Annotated[float, pydantic.Field(description='Maximum distortion, in percent.')]


_WIZARD_VALUES_SCHEMA: dict[str, object] = dict(pydantic.TypeAdapter(OptimizationWizardSettings).json_schema())
_WIZARD_VALUES_SCHEMA.pop('title', None)
_WIZARD_VALUES_SCHEMA['additionalProperties'] = False
_WIZARD_VALUES_SCHEMA['description'] = (
    'Wizard controls to change. Omit this argument to keep every dialog default.'
)

_wizard_setting_names = [item.name for item in zemaxmcp.opticstudio._WIZARD_SETTINGS]

if list(OptimizationWizardSettings.__annotations__) != _wizard_setting_names:
    raise RuntimeError('Optimization wizard settings do not match the tool schema.')


def create_server() -> mcp.server.MCPServer:
    """
    Create an MCP server.

    The server connects to Interactive Extension on the first call that needs it.

    :returns: The server.
    :rtype: mcp.server.MCPServer
    """

    server = mcp.server.MCPServer(SERVER_NAME, lifespan=lifespan)

    def read(ctx, load):
        """
        Run one read against the shared session.

        The session is dropped when OpticStudio cannot answer, so the next call can reconnect.

        :param ctx: Tool context for this request.
        :param load: Called with the open session.
        :returns: The value returned by ``load``.
        :raises mcp.server.mcpserver.exceptions.ToolError: OpticStudio cannot answer.
        """

        # Drop the shared session when OpticStudio cannot answer, so the next call can reconnect.
        connection = ctx.request_context.lifespan_context

        try:
            return load(connection.open())
        except zemaxmcp.opticstudio.OpticStudioError as exc:
            connection.close()
            raise mcp.server.mcpserver.exceptions.ToolError(str(exc)) from exc

    @server.tool(
        description='Return version, license, and connection details for the OpticStudio window.',
    )
    def get_opticstudio_version(ctx: mcp.server.mcpserver.Context) -> dict[str, str | int]:
        """
        Return version details for the OpticStudio window waiting on Interactive Extension.

        :returns:
            * **product_name** -- Product name from ``OpticStudio.exe``.
            * **product_version** -- Product version, such as ``24.2.00.0``. The first two parts identify the release, so 24.2 is 2024 R2.
            * **file_version** -- File version of ``OpticStudio.exe``.
            * **file_description** -- File description of ``OpticStudio.exe``.
            * **opticstudio_version** -- Integer version reported by ZOS-API.
            * **zos_major_version** -- ZOS-API major version.
            * **zos_minor_version** -- ZOS-API minor version.
            * **zos_service_pack** -- ZOS-API service pack number. 0 means no service pack.
            * **license_status** -- License type, such as ``PremiumEdition``.
            * **mode** -- Connection mode. Interactive Extension reports ``Plugin``.
            * **installation_directory** -- Directory that contains ``OpticStudio.exe``.
            * **supported_release** -- Release this server supports. This value is fixed by the server.
        :rtype: dict[str, str | int]
        """

        return read(ctx, lambda session: session.version())

    @server.tool(
        description='Return the identity of the lens, including whether it has unsaved changes.',
    )
    def get_lens_metadata(ctx: mcp.server.mcpserver.Context) -> dict[str, str | bool]:
        """
        Return identity details for the lens open in the OpticStudio window.

        :returns:
            * **file** -- Full path of the lens file. Empty when the lens has not been saved.
            * **name** -- System name.
            * **title** -- Lens title from System Explorer Title/Notes.
            * **author** -- Author from System Explorer Title/Notes.
            * **notes** -- Notes from System Explorer Title/Notes.
            * **mode** -- ``Sequential`` or ``NonSequential``.
            * **needs_save** -- True when the window has unsaved changes.
            * **is_project_directory** -- True when the lens is stored as a project directory rather than a single file.
        :rtype: dict[str, str | bool]
        """

        return read(ctx, lambda session: session.lens_file())

    @server.tool(
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

        return read(ctx, lambda session: session.system_data(section))

    @server.tool(
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

        return read(ctx, lambda session: session.set_system_data(section, values))

    @server.tool(
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

        return read(ctx, lambda session: session.set_system_rows(section, action, number, values))

    @server.tool(
        description='Return the Lens Data Editor surfaces, or one surface when `surface` is given.',
    )
    def get_lens_data(
        ctx: mcp.server.mcpserver.Context,
        surface: int | None = None,
    ) -> dict[str, object]:
        """
        Return the Lens Data Editor surfaces for the lens open in the OpticStudio window.

        Pass ``surface`` to read one surface. Omit it to read every surface.

        :param surface: Surface number. 0 is the object surface. ``None`` reads every surface.
        :returns: Without ``surface``, ``surfaces``. With ``surface``, that surface.

            * **surfaces** -- One entry per surface, starting with the object surface at surface 0. Present when ``surface`` is omitted.
            * **surface_number** -- Surface number. 0 is the object surface.
            * **is_stop** -- True when the surface is the stop.
            * **type** -- Surface type, such as ``Standard`` or ``EvenAspheric``.
            * **parameters** -- Parameter columns used by ``type``. Empty when the type uses none.
            * **parameters[].column** -- Column name, such as ``Par1``.
            * **parameters[].header** -- Column title from the Lens Data Editor. This member is read-only.
            * **parameters[].value** -- Cell value. A number, or a string when the cell stores text.
            * **comment** -- Surface comment. Empty when the surface has no comment.
            * **radius** -- Radius of curvature, in lens units.
            * **thickness** -- Thickness to the next surface, in lens units.
            * **material** -- Glass name. Empty when the surface is air.
            * **coating** -- Coating name. Empty when the surface has no coating.
            * **semi_diameter** -- Clear semi-diameter, in lens units.
            * **chip_zone** -- Chip zone, in lens units.
            * **mechanical_semi_diameter** -- Mechanical semi-diameter, in lens units.
            * **conic** -- Conic constant.
            * **tce** -- Thermal coefficient of expansion stored for the surface.
        :rtype: dict[str, object]
        :raises ValueError: ``surface`` is outside the editor.
        """

        return read(ctx, lambda session: session.lens_data(surface))

    @server.tool(
        description=(
            'Change, insert, or remove one surface in the Lens Data Editor. '
            '`action` is `change`, `add`, or `remove`. '
            '`number` is the surface number, and `0` is the object surface. '
            '`add` inserts a surface at `number`. '
            '`values` uses the same fields as one surface returned by `get_lens_data`. '
            '`type` sets the surface type. '
            '`parameters` maps column names such as `Par1` to new values. '
            'When both are set, the type changes first.'
        ),
    )
    def set_lens_rows(
        ctx: mcp.server.mcpserver.Context,
        action: typing.Literal['change', 'add', 'remove'],
        number: int,
        values: dict[str, str | float | bool | int | dict[str, str | float | int]] | None = None,
    ) -> dict[str, object]:
        """
        Change, insert, or remove one Lens Data Editor surface and return the editor.

        :param action: ``change``, ``add``, or ``remove``.
        :param number: Surface number. 0 is the object surface. ``add`` inserts at this number, and following surfaces move up. The inserted surface is ``Standard`` until ``values`` sets ``type``.
        :param values: Keys to write. The fields are the same as those of one surface returned by :meth:`get_lens_data`. Omit ``values`` to insert a default surface or to remove a surface. ``surface_number`` is read-only. ``type`` is a surface type name, such as ``EvenAspheric``. ``parameters`` maps column names such as ``Par1`` to a number or a string; only listed columns are written, and ``header`` is read-only. ``type`` is applied before ``parameters``. Setting ``is_stop`` to true makes that surface the stop. The object and image surfaces cannot be removed.
        :returns: The surfaces after the change.
        :rtype: dict[str, object]
        :raises ValueError: The action, number, or values cannot be applied.
        """

        return read(ctx, lambda session: session.set_lens_rows(action, number, values))

    @server.tool(
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

        return read(ctx, lambda session: session.merit_function(operand))

    @server.tool(
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

        return read(ctx, lambda session: session.set_merit_rows(action, number, values))

    @server.tool(
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
        :rtype: dict[str, object]
        :raises ValueError: ``operand`` is outside the editor.
        """

        return read(ctx, lambda session: session.multi_configuration(operand))

    @server.tool(
        description=(
            'Change the Multi-Configuration Editor. '
            '`section` is `operand` or `configuration`. '
            '`action` is `change`, `add`, `remove`, or `make_current`. '
            '`make_current` selects the configuration shown in the Lens Data Editor. '
            '`values` uses the same fields as one operand returned by `get_multi_configuration`. '
            '`type` sets the operand type before parameters and configuration cells.'
        ),
    )
    def set_multi_configuration_rows(
        ctx: mcp.server.mcpserver.Context,
        section: typing.Literal['operand', 'configuration'],
        action: typing.Literal['change', 'add', 'remove', 'make_current'],
        number: int,
        values: dict[str, str | float | bool | int | dict[str, str | float | int]] | None = None,
    ) -> dict[str, object]:
        """
        Change one Multi-Configuration Editor operand or configuration and return the editor.

        :param section: ``operand`` or ``configuration``.
        :param action: ``change``, ``add``, ``remove``, or ``make_current``. ``make_current`` selects the configuration shown in the Lens Data Editor.
        :param number: 1-based operand or configuration number. ``add`` inserts at this number, and following rows or columns move up. Pass ``number`` one past the last entry to append.
        :param values: Keys to write. For an operand, the fields are the same as those of one operand returned by :meth:`get_multi_configuration`. Omit ``values`` to insert a default operand or configuration, or to remove one. ``number`` and ``active`` are read-only. ``type`` is an operand type name, such as ``THIC``. ``parameters`` maps ``Param1``, ``Param2``, or ``Param3`` to an integer. ``cells`` maps a configuration number, such as ``"1"``, to a number or a string. ``type`` is applied before ``parameters`` and ``cells``. A configuration has no fields to change. ``add`` for a configuration accepts ``copy``: true copies the current configuration's cells. The last configuration cannot be removed.
        :returns: ``current``, ``configurations``, and ``operands`` after the change.
        :rtype: dict[str, object]
        :raises ValueError: The section, action, number, or values cannot be applied.
        """

        return read(
            ctx,
            lambda session: session.set_multi_configuration_rows(section, action, number, values),
        )

    @server.tool(
        description=(
            'Apply the Optimization Wizard and return the operands it creates. '
            'Omit `values` to use the wizard defaults. '
            'Each property of `values` is one wizard control. '
            'Operands from the Start At row through the end of the editor are replaced.'
        ),
    )
    def apply_optimization_wizard(
        ctx: mcp.server.mcpserver.Context,
        values: typing.Annotated[
            OptimizationWizardSettings | None,
            pydantic.WithJsonSchema(_WIZARD_VALUES_SCHEMA),
        ] = None,
    ) -> dict[str, object]:
        """
        Apply the Optimization Wizard and return the settings and operands.

        The wizard is reset to its dialog defaults. Keys in ``values`` then replace those defaults. Omit ``values`` to keep every default. Operands from ``start_at`` through the end of the editor are replaced.

        :param values: Wizard controls to change. Omit it to use the dialog defaults. A glass or air thickness turns that boundary on when its checkbox is omitted. ``configuration`` selects one configuration, and ``field`` selects one field, when the matching "all" checkbox is omitted.
        :returns:
            * **settings** -- Wizard controls that were applied, including defaults that ``values`` did not change.
            * **settings.criterion** -- ``Wavefront``, ``Contrast``, ``Spot`` for spot radius, or ``Angular`` for angular radius.
            * **settings.type** -- ``RMS`` or ``PTV``.
            * **settings.reference** -- ``Centroid``, ``ChiefRay``, or ``Unreferenced``.
            * **settings.spatial_frequency** -- Spatial frequency used when ``criterion`` is ``Contrast``. The unit follows the lens MTF units.
            * **settings.xs_weight** -- XS contrast weight.
            * **settings.yt_weight** -- YT contrast weight.
            * **settings.pupil_integration** -- ``GaussianQuadrature`` or ``RectangularArray``. This selects the pupil sampling. Setting one turns the other off.
            * **settings.rings** -- Ring count for Gaussian quadrature. An integer of at least 1.
            * **settings.arms** -- Arm count for Gaussian quadrature: ``6``, ``8``, ``10``, or ``12``.
            * **settings.obscuration** -- Pupil obscuration for Gaussian quadrature, as shown in the wizard.
            * **settings.grid_size** -- Points along one side of the rectangular sampling grid. An integer of at least 1. Used when ``pupil_integration`` is ``RectangularArray``.
            * **settings.delete_vignetted** -- True when vignetted rays are deleted.
            * **settings.use_glass_boundaries** -- True when glass boundary operands are added.
            * **settings.glass_min** -- Minimum glass thickness, in lens units.
            * **settings.glass_max** -- Maximum glass thickness, in lens units.
            * **settings.glass_edge** -- Minimum glass edge thickness, in lens units.
            * **settings.use_air_boundaries** -- True when air boundary operands are added.
            * **settings.air_min** -- Minimum air thickness, in lens units.
            * **settings.air_max** -- Maximum air thickness, in lens units.
            * **settings.air_edge** -- Minimum air edge thickness, in lens units.
            * **settings.start_at** -- 1-based operand row where the new operands begin.
            * **settings.overall_weight** -- Weight applied to the generated operands.
            * **settings.use_all_configurations** -- True when operands are built for every configuration.
            * **settings.configuration** -- 1-based configuration number used when ``use_all_configurations`` is false.
            * **settings.use_all_fields** -- True when operands are built for every field.
            * **settings.field** -- 1-based field number used when ``use_all_fields`` is false.
            * **settings.assume_axial_symmetry** -- True when the wizard assumes axial symmetry.
            * **settings.ignore_lateral_color** -- True when lateral color is ignored.
            * **settings.add_favorite_operands** -- True when favorite operands are added.
            * **settings.optimize_for_best_nominal_performance** -- True when the wizard optimizes the nominal design.
            * **settings.optimize_for_manufacturing_yield** -- True when manufacturing yield is included.
            * **settings.manufacturing_yield_weight** -- Weight of the manufacturing-yield target.
            * **settings.use_maximum_distortion** -- True when distortion is limited.
            * **settings.maximum_distortion** -- Maximum distortion, in percent.
            * **operands** -- One entry per operand after the wizard runs. The fields of each operand are the same as those returned by :meth:`get_merit_function`. ``value`` and ``contribution`` are not calculated.
        :rtype: dict[str, object]
        :raises ValueError: A wizard setting cannot be applied.
        """

        return read(ctx, lambda session: session.apply_optimization_wizard(values))

    @server.tool(
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

        return read(ctx, lambda session: session.calculate_merit_function())

    @server.tool(
        description=(
            'Return the Single Ray Trace table for one ray. '
            '`hx` and `hy` are the normalized field coordinates. '
            '`px` and `py` are the normalized pupil coordinates. '
            '`trace_type` is `DirectionCosines`, `TangentAngle`, or `YmUmYcUc`.'
        ),
    )
    def get_single_ray_trace(
        ctx: mcp.server.mcpserver.Context,
        wavelength: int = 1,
        hx: float = 0,
        hy: float = 0,
        px: float = 0,
        py: float = 0,
        trace_type: typing.Literal['DirectionCosines', 'TangentAngle', 'YmUmYcUc'] = 'DirectionCosines',
    ) -> dict[str, object]:
        """
        Return the Single Ray Trace table for one ray in the open lens.

        ``hx`` and ``hy`` are the normalized field coordinates. ``px`` and ``py`` are the normalized pupil coordinates. ``trace_type`` selects Direction Cosines, Tangential Angle, or ``Ym, Um, Yc, Uc``.

        :param wavelength: 1-based wavelength number.
        :param hx: Normalized field coordinate X.
        :param hy: Normalized field coordinate Y.
        :param px: Normalized pupil coordinate X.
        :param py: Normalized pupil coordinate Y.
        :param trace_type: ``DirectionCosines``, ``TangentAngle``, or ``YmUmYcUc``.
        :returns:
            * **wavelength** -- Wavelength number used for the ray.
            * **hx** -- Normalized field coordinate X.
            * **hy** -- Normalized field coordinate Y.
            * **px** -- Normalized pupil coordinate X.
            * **py** -- Normalized pupil coordinate Y.
            * **type** -- Table format.
            * **columns** -- Headings of the Single Ray Trace table, after the surface column.
            * **surfaces** -- One entry per surface, in the order shown in the window.
            * **surfaces[].surface** -- Surface label from the table, such as ``OBJ``, a surface number, or ``IMA``.
            * **surfaces[].values** -- One number per heading. ``None`` where the table has no finite number.
            * **message** -- Error line under the table. Empty when the table has none.
        :rtype: dict[str, object]
        :raises ValueError: The ray settings or the table cannot be used.
        """

        return read(
            ctx,
            lambda session: session.single_ray_trace(wavelength, hx, hy, px, py, trace_type),
        )

    @server.tool(
        description=(
            'Return effective focal length, entrance pupil diameter, F-numbers, and total length for the open lens. '
            'Lengths are in lens units.'
        ),
    )
    def get_first_order(ctx: mcp.server.mcpserver.Context) -> dict[str, float | str | None]:
        """
        Return first-order values for the lens open in the OpticStudio window.

        The system is updated before the values are read. ``working_f_number`` is on axis at the primary wavelength. A number is ``None`` when OpticStudio does not return a finite value.

        :returns:
            * **effective_focal_length** -- Effective focal length, in lens units.
            * **entrance_pupil_diameter** -- Entrance pupil diameter, in lens units.
            * **image_space_f_number** -- Paraxial image-space F-number.
            * **working_f_number** -- Working F-number on axis at the primary wavelength.
            * **total_length** -- Thickness from surface 1 to the image surface, in lens units.
            * **status** -- Text reported while updating the system. Empty when the update reports nothing.
        :rtype: dict[str, float | str | None]
        """

        return read(ctx, lambda session: session.first_order())

    @server.tool(
        description=(
            'Save the open lens. Omit `path` to save the current file. '
            'Pass a full `path` to save it as a new file. '
            'An existing file at that path is replaced.'
        ),
    )
    def save_lens(
        ctx: mcp.server.mcpserver.Context,
        path: str | None = None,
    ) -> dict[str, str | bool]:
        """
        Save the lens open in the OpticStudio window and return its identity.

        Omit ``path`` to save the current file. Pass a full path to save the lens as a new file. The window then uses that file. An existing file at that path is replaced. A lens that has never been saved needs a path.

        :param path: Full path of the new lens file, such as a ``.zmx`` or ``.zos`` file. ``None`` saves the current file.
        :returns: The lens identity after the save. The fields are the same as those returned by :meth:`get_lens_metadata`.
        :rtype: dict[str, str | bool]
        :raises ValueError: The lens has no current file, ``path`` is not a full path, or OpticStudio cannot save.
        """

        return read(ctx, lambda session: session.save(path))

    return server


def main() -> None:
    """Serve MCP over stdio until the host closes the connection."""

    create_server().run()
