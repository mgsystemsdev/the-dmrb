from db.errors import DatabaseIntegrityError
from db import repository


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _DriftedPostgresConn:
    engine = "postgres"

    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql == "INSERT INTO property (name) VALUES (%s) RETURNING property_id":
            raise DatabaseIntegrityError(
                'null value in column "property_id" of relation "property" violates not-null constraint'
            )
        if sql == "LOCK TABLE property IN EXCLUSIVE MODE":
            return _FakeCursor(None)
        if sql == "SELECT COALESCE(MAX(property_id), 0) + 1 AS next_property_id FROM property":
            return _FakeCursor({"next_property_id": 7})
        if sql == "INSERT INTO property (property_id, name) VALUES (%s, %s) RETURNING property_id":
            return _FakeCursor({"property_id": 7})
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_insert_property_falls_back_when_postgres_property_identity_is_missing():
    conn = _DriftedPostgresConn()

    property_id = repository.insert_property(conn, "Thousand Oaks")

    assert property_id == 7
    assert conn.calls == [
        ("INSERT INTO property (name) VALUES (%s) RETURNING property_id", ("Thousand Oaks",)),
        ("LOCK TABLE property IN EXCLUSIVE MODE", None),
        ("SELECT COALESCE(MAX(property_id), 0) + 1 AS next_property_id FROM property", None),
        ("INSERT INTO property (property_id, name) VALUES (%s, %s) RETURNING property_id", (7, "Thousand Oaks")),
    ]
