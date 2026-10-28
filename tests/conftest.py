import pytest

from scaneu import create_app
from scaneu.db import connect, init_schema, seed_demo


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "DATABASE": str(tmp_path / "test.db"),
        "IMAGE_DIR": str(tmp_path / "images"),
        "SIMULATOR": True,
    })
    conn = connect(app.config["DATABASE"])
    init_schema(conn)
    seed_demo(conn)
    conn.close()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()
