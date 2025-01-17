import asyncio
import sys

import pytest

from flask import Blueprint
from flask import Flask
from flask import request
from flask.helpers import run_async

pytest.importorskip("asgiref")


class AppError(Exception):
    pass


class BlueprintError(Exception):
    pass


@pytest.fixture(name="async_app")
def _async_app():
    app = Flask(__name__)

    @app.route("/", methods=["GET", "POST"])
    async def index():
        await asyncio.sleep(0)
        return request.method

    @app.errorhandler(AppError)
    async def handle(_):
        return "", 412

    @app.route("/error")
    async def error():
        raise AppError()

    blueprint = Blueprint("bp", __name__)

    @blueprint.route("/", methods=["GET", "POST"])
    async def bp_index():
        await asyncio.sleep(0)
        return request.method

    @blueprint.errorhandler(BlueprintError)
    async def bp_handle(_):
        return "", 412

    @blueprint.route("/error")
    async def bp_error():
        raise BlueprintError()

    app.register_blueprint(blueprint, url_prefix="/bp")

    return app


@pytest.mark.skipif(sys.version_info < (3, 7), reason="requires Python >= 3.7")
@pytest.mark.parametrize("path", ["/", "/bp/"])
def test_async_route(path, async_app):
    test_client = async_app.test_client()
    response = test_client.get(path)
    assert b"GET" in response.get_data()
    response = test_client.post(path)
    assert b"POST" in response.get_data()


@pytest.mark.skipif(sys.version_info < (3, 7), reason="requires Python >= 3.7")
@pytest.mark.parametrize("path", ["/error", "/bp/error"])
def test_async_error_handler(path, async_app):
    test_client = async_app.test_client()
    response = test_client.get(path)
    assert response.status_code == 412


@pytest.mark.skipif(sys.version_info < (3, 7), reason="requires Python >= 3.7")
def test_async_before_after_request():
    app_first_called = False
    app_before_called = False
    app_after_called = False
    bp_before_called = False
    bp_after_called = False

    app = Flask(__name__)

    @app.route("/")
    def index():
        return ""

    @app.before_first_request
    async def before_first():
        nonlocal app_first_called
        app_first_called = True

    @app.before_request
    async def before():
        nonlocal app_before_called
        app_before_called = True

    @app.after_request
    async def after(response):
        nonlocal app_after_called
        app_after_called = True
        return response

    blueprint = Blueprint("bp", __name__)

    @blueprint.route("/")
    def bp_index():
        return ""

    @blueprint.before_request
    async def bp_before():
        nonlocal bp_before_called
        bp_before_called = True

    @blueprint.after_request
    async def bp_after(response):
        nonlocal bp_after_called
        bp_after_called = True
        return response

    app.register_blueprint(blueprint, url_prefix="/bp")

    test_client = app.test_client()
    test_client.get("/")
    assert app_first_called
    assert app_before_called
    assert app_after_called
    test_client.get("/bp/")
    assert bp_before_called
    assert bp_after_called


@pytest.mark.skipif(sys.version_info >= (3, 7), reason="should only raise Python < 3.7")
def test_async_runtime_error():
    with pytest.raises(RuntimeError):
        run_async(None)
