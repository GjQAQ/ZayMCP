"""
Stdio MCP server.
"""

import contextlib
import typing

import mcp.server
import mcp.server.mcpserver
import mcp.server.mcpserver.exceptions

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

    return server


def main() -> None:
    """Serve MCP over stdio until the host closes the connection."""

    create_server().run()
