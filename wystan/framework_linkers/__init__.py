"""Stage 6.4 framework-aware linkers.

Each linker is a class that implements :class:`FrameworkLinker` and
adapts ONE framework-specific coupling pattern into a uniform
:class:`FrameworkLink` stream consumed by Stage 6.4.

v1 (Sprint C4) ships :class:`NextjsHttpRouteLinker` only. Future
linkers — Server Actions, Zustand, Redux, tRPC — plug in via Python
entry-points under the ``wystan.framework_linkers`` group:

.. code-block:: toml

    [project.entry-points."wystan.framework_linkers"]
    nextjs-http-route = "wystan.framework_linkers.nextjs_http_route:NextjsHttpRouteLinker"

Adding a new linker MUST NOT modify the existing ``Protocol`` contract
in :mod:`base` — it is FROZEN once Stage 6.4 ships.
"""

from wystan.framework_linkers.base import (
    FrameworkLink,
    FrameworkLinker,
)

__all__ = ["FrameworkLink", "FrameworkLinker"]
