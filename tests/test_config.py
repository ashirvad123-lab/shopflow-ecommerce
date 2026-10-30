from pathlib import Path

from sqlalchemy.engine import make_url

from config import BASE_DIR, normalize_database_url


def test_relative_sqlite_url_resolves_to_instance_database():
    url = normalize_database_url('sqlite:///ecommerce.db')

    assert Path(make_url(url).database) == (BASE_DIR / 'instance' / 'ecommerce.db').resolve()


def test_sqlite_memory_url_remains_in_memory():
    assert normalize_database_url('sqlite:///:memory:') == 'sqlite:///:memory:'
