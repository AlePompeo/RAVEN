# SPDX-License-Identifier: Apache-2.0
"""Historical HTTP oracle for regression tests, never registered by production.

The frozen pre-RAVEN contracts retain their original parameters and numbers. Only
golden generation and historical tests use this factory; live routes return 410.
"""

from fastapi import FastAPI


def build_reference_app() -> FastAPI:
    from backend.bootstrap import build_app
    from scripts.raven_reference.grazing_routes import include_grazing_routes
    from scripts.raven_reference.lunar_routes import include_lunar_routes

    app = build_app()
    existing = app.router.routes.copy()
    include_lunar_routes(app)
    include_grazing_routes(app)
    app.router.routes[:] = app.router.routes[len(existing) :] + existing
    return app
