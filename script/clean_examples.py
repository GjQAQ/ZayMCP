"""Delete Zemax files saved in examples/."""

from pathlib import Path

__all__ = [
    'main',
]

# OpticStudio writes a lens, an archive, and a session cache beside a saved example.
_SUFFIXES = frozenset({'.zmx', '.zos', '.zda'})


def main() -> None:
    """Delete ``.zmx``, ``.zos``, and ``.zda`` files directly under ``examples/``."""
    root = Path(__file__).resolve().parent.parent
    examples = root / 'examples'

    if not examples.is_dir():
        raise SystemExit(f'{examples} does not exist.')

    removed = []

    for path in sorted(examples.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _SUFFIXES:
            continue

        path.unlink()
        removed.append(path.relative_to(root))

    if not removed:
        print('No Zemax files in examples/.')
        return

    for path in removed:
        print(path)


if __name__ == '__main__':
    main()
