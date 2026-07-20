"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from bluefish.store.db import Store


@pytest.fixture()
def store(tmp_path):
    db = Store(tmp_path / "test.db")
    yield db
    db.close()
