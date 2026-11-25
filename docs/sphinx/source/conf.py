import inspect
import sys
import typing
from pathlib import Path

import sphinx.util.inspect

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

project = "ZayMCP"
copyright = "2026, Jiaqi Guo"
author = "Jiaqi Guo"
version = "0.1.0"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
]

autodoc_typehints = "signature"
autodoc_typehints_format = "short"
add_module_names = False
python_display_short_literal_types = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

exclude_patterns = []

html_theme = "furo"
html_theme_options = {
    "source_repository": "https://github.com/GjQAQ/ZayMCP/",
    "source_branch": "main",
    "source_directory": "docs/sphinx/source/",
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/GjQAQ/ZayMCP",
            "html": """
                <svg stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path>
                </svg>
            """,
            "class": "",
        },
    ],
}
html_title = "ZayMCP"


def _annotation_for_docs(annotation):
    if annotation is inspect.Parameter.empty:
        return annotation

    if typing.get_origin(annotation) is typing.Annotated:
        return typing.get_args(annotation)[0]

    return annotation


def _present_signature(app, what, name, obj, options, signature, return_annotation):
    """Show an annotated type without the schema metadata attached to it."""

    if not signature or "Annotated[" not in signature:
        return None

    try:
        original = inspect.signature(obj)
    except (TypeError, ValueError):
        return None

    parameters = [
        parameter.replace(annotation=_annotation_for_docs(parameter.annotation))
        for parameter in original.parameters.values()
    ]
    cleaned = original.replace(parameters=parameters)
    rendered = sphinx.util.inspect.stringify_signature(
        cleaned,
        show_return_annotation=False,
        unqualified_typehints=True,
        short_literals=True,
    )

    return rendered, return_annotation


def _resolve_unique_python_name(app, env, node, contnode):
    """Link a bare name when exactly one documented object has that name."""

    if node.get("refdomain") != "py":
        return None

    target = node.get("reftarget") or ""

    if not target or "." in target:
        return None

    domain = env.domains["py"]
    matches = [
        name
        for name in domain.objects
        if name == target or name.endswith("." + target)
    ]

    if len(matches) != 1:
        return None

    return domain.resolve_xref(
        env,
        node["refdoc"],
        app.builder,
        node["reftype"],
        matches[0],
        node,
        contnode,
    )


def setup(app):
    app.connect("autodoc-process-signature", _present_signature)
    app.connect("missing-reference", _resolve_unique_python_name)
