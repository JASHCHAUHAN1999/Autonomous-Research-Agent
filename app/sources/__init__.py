"""Source adapter package.

Importing this package must populate ``base.REGISTRY`` with every adapter.
The four adapter modules (tavily, wikipedia, news, web) each call
``register()`` at import time, so importing them here is what fills the
registry. Those modules are added in their own tasks; until they exist we
only import ``base`` so the package imports cleanly.
"""
from app.sources import base  # noqa: F401

# NOTE: Uncomment as each adapter module lands (Tasks 3-6). Each import triggers
# that module's register() call, adding it to base.REGISTRY.
from app.sources import tavily  # noqa: F401,E402
from app.sources import wikipedia  # noqa: F401,E402
from app.sources import news  # noqa: F401,E402
from app.sources import web_scraper  # noqa: F401,E402
