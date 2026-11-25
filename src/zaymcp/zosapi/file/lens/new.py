"""Create a new lens in the OpticStudio window."""

from zaymcp.zosapi.errors import OpticStudioError


def _new_lens(system, discard_changes: bool) -> None:
    # New(False) resets the primary system in place and does not save it.
    if not isinstance(discard_changes, bool):
        raise ValueError('discard_changes must be true or false.')

    try:
        needs_save = bool(system.NeedsSave)
    except OpticStudioError:
        raise
    except Exception as exc:
        raise ValueError(f'The lens could not be created. {exc}') from exc

    if needs_save and not discard_changes:
        raise ValueError('The lens has unsaved changes. Save it, or pass discard_changes to replace it.')

    try:
        system.New(False)
    except OpticStudioError:
        raise
    except Exception as exc:
        raise ValueError(f'The lens could not be created. {exc}') from exc
