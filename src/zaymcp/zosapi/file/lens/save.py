"""Save the lens open in the OpticStudio window."""

import os

from zaymcp.zosapi.errors import OpticStudioError
from zaymcp.zosapi.model.fields import text

def _save_path(path: str) -> str:
    if not isinstance(path, str):
        raise ValueError('path must be a full file path.')

    filename = path.strip()

    if not filename or not os.path.isabs(filename):
        raise ValueError('path must be a full file path.')

    return filename


def _save_lens(system, path: str | None) -> None:
    # A failed save leaves the Interactive Extension session open, so this raises ValueError.
    if path is None:
        if text(system.SystemFile) == '':
            raise ValueError('The lens has not been saved. Pass path to save it as a new file.')

        try:
            system.Save()
        except OpticStudioError:
            raise
        except Exception as exc:
            raise ValueError(f'The lens could not be saved. {exc}') from exc

        return

    filename = _save_path(path)

    try:
        system.SaveAs(filename)
    except OpticStudioError:
        raise
    except Exception as exc:
        raise ValueError(f'The lens could not be saved. {exc}') from exc
