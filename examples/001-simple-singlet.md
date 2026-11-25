# 001 Simple Singlet

Use zaymcp to design a simple positive singlet. Create a new sequential lens, save it as specified below, and then follow the specification, the starting prescription, and the acceptance criteria.

## File

Save the new lens as `examples/001-simple-singlet.zmx` before changing it. Pass the full path of that file. Save it even when `needs_save` is false. Overwrite the file if it already exists.

## Specification

Design a positive singlet that focuses an on-axis object at infinity onto the image surface.

| Item | Requirement |
| --- | --- |
| Units | Millimeters |
| Entrance pupil diameter | 20 |
| Effective focal length | 100 |
| Field | One field, angle, on axis, weight 1 |
| Wavelength | One wavelength, 0.5875618 μm, set as the primary |
| Construction | One N-BK7 standard spherical lens. The stop is on the first optical surface |
| Glass thickness | 5, fixed |
| Variables | Both radii of curvature, and the air gap from the lens to the image |

The object is at infinity. Set the material to `N-BK7`. Stop and report the reason if that name cannot be written. Keep this single glass element. Do not add surfaces. Do not switch to aspheres.

## Starting prescription

Fill the table below into a new sequential lens. These numbers are deliberately out of focus. Leave them unchanged until optimization.

| Surface | Radius | Thickness | Material | Variables |
| --- | --- | --- | --- | --- |
| Object | Infinity | Infinity | | |
| 1 | 100 | 5 | N-BK7 | Radius |
| 2 | −100 | 50 | | Radius, thickness |
| Image | | | | |

The stop is on surface 1.

## Merit function and optimization

The merit function contains both of these: an effective-focal-length target of 100, and the RMS spot radius about the centroid at that field and wavelength. Keep the focal-length operand in the merit function. The wizard replaces operands from its start row through the end, so place the focal-length operand outside that range.

Then run local optimization with damped least squares and automatic cycles. If the criteria below are not met, run once more with the same settings. If they are still not met, stop and report. Do not change the specification, the glass, or the variables.

## Acceptance criteria

- The effective focal length is within 0.5 of 100.
- The merit function before and after optimization is finite, and the final value is no greater than one tenth of the initial value.
- Both radii and the thickness of surface 2 remain variables.
- Save the finished lens to the same path. Overwrite the file.

Report the effective focal length, the image-space F-number, the merit function before and after, the final two radii and both thicknesses, and the save path.
