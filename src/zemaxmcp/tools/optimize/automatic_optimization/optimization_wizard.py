"""Optimization Wizard tool."""

import typing

import mcp.server.mcpserver
import pydantic

import zemaxmcp.server as mcp_server
import zemaxmcp.zosapi.optimize.automatic_optimization.optimization_wizard as wizard

__all__ = [
    'apply_optimization_wizard',
]

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

_wizard_setting_names = list(wizard.SETTING_NAMES)

if list(OptimizationWizardSettings.__annotations__) != _wizard_setting_names:
    raise RuntimeError('Optimization wizard settings do not match the tool schema.')

@mcp_server.server.tool(
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

    return mcp_server.read(ctx, lambda session: session.apply_optimization_wizard(values))
