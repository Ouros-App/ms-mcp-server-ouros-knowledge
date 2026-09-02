import unittest
from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Self
from unittest.mock import patch

from app.services.database import (
    _json_safe,
    _rows,
    get_user_context,
    get_user_farm_data,
    import_resource_records,
    postgres_status,
)


class FakeCursor:
    def __init__(self, responses: list[object]) -> None:
        self.responses = iter(responses)
        self.current: object = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, *_args: object) -> "FakeCursor":
        self.current = next(self.responses)
        return self

    def fetchone(self) -> object:
        return self.current

    def fetchall(self) -> list:
        return self.current if isinstance(self.current, list) else []


class FakeConnection:
    def __init__(
        self, cursor: FakeCursor | None = None, row: dict | None = None
    ) -> None:
        self.fake_cursor = cursor
        self.row = row

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        assert self.fake_cursor is not None
        return self.fake_cursor

    def execute(self, *_args: object) -> SimpleNamespace:
        return SimpleNamespace(fetchone=lambda: self.row)


class DatabaseGuardTests(unittest.TestCase):
    @patch("app.services.database._connect")
    def test_import_resource_records_calls_controlled_function(self, connect) -> None:
        cursor = FakeCursor([])
        connection = FakeConnection(cursor, {"result": {"request_id": "abc", "status": "accepted"}})
        connect.return_value = connection

        result = import_resource_records(
            "farm_owner", 42, "00000000-0000-0000-0000-000000000001", "excel", "historico.xlsx", [
                {"resource_type": "energy", "farm_id": 8,
                 "registration_date": "2025-01-31", "energy_consumption": 12.5,
                 "source_row": 2, "confidence": 1.0}
            ]
        )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(connect.call_count, 1)

    def test_import_resource_records_rejects_unsupported_input_before_connecting(self) -> None:
        with patch("app.services.database._connect") as connect:
            with self.assertRaises(ValueError):
                import_resource_records("company_employee", 42, "abc", "excel", "x", [])  # type: ignore[arg-type]
            connect.assert_not_called()

    def test_json_safe_converts_postgres_values(self) -> None:
        value = _json_safe(
            {
                "date": date(2026, 8, 25),
                "datetime": datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc),
                "time": time(10, 30),
                "amount": Decimal("1.5"),
                "items": (Decimal("2.5"),),
            }
        )

        self.assertEqual(
            value,
            {
                "date": "2026-08-25",
                "datetime": "2026-08-25T10:30:00+00:00",
                "time": "10:30:00",
                "amount": 1.5,
                "items": [2.5],
            },
        )

    def test_rows_sanitizes_dict_rows(self) -> None:
        cursor = SimpleNamespace(fetchall=lambda: [{"amount": Decimal("3.2")}])

        self.assertEqual(_rows(cursor), [{"amount": 3.2}])

    @patch("app.services.database._connect")
    def test_invalid_user_does_not_open_database_connection(self, connect) -> None:
        with self.assertRaises(ValueError):
            get_user_context("unknown", 1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            get_user_farm_data("farm_owner", 0)

        connect.assert_not_called()

    @patch("app.services.database._connect")
    def test_postgres_status_reports_success(self, connect) -> None:
        connect.return_value = FakeConnection(
            row={"database": "second", "user": "midas_ro"}
        )

        self.assertEqual(
            postgres_status(),
            {"connected": True, "database": "second", "user": "midas_ro"},
        )

    @patch("app.services.database._connect", side_effect=ConnectionError)
    def test_postgres_status_hides_connection_error(self, _connect) -> None:
        self.assertEqual(
            postgres_status(),
            {"connected": False, "error": "ConnectionError"},
        )

    @patch("app.services.database._connect")
    def test_user_context_scopes_farm_owner(self, connect) -> None:
        cursor = FakeCursor(
            [
                {
                    "user_id": 42,
                    "name": "Owner",
                    "farm_id": 8,
                    "enterprise_id": 3,
                },
                [{"id": 3, "name": "Enterprise"}],
                [{"id": 8, "name": "Farm"}],
            ]
        )
        connect.return_value = FakeConnection(cursor)

        result = get_user_context("farm_owner", 42)

        self.assertEqual(result["enterprises"], [{"id": 3, "name": "Enterprise"}])
        self.assertEqual(result["farms"], [{"id": 8, "name": "Farm"}])

    @patch("app.services.database._connect")
    def test_user_context_scopes_employee_and_admin(self, connect) -> None:
        employee_cursor = FakeCursor(
            [
                {"user_id": 5, "enterprise_id": 3},
                [{"id": 8}],
                [{"id": 3, "name": "Enterprise"}],
                [{"id": 8, "name": "Farm"}],
            ]
        )
        connect.return_value = FakeConnection(employee_cursor)
        employee = get_user_context("company_employee", 5)
        self.assertEqual(employee["farms"], [{"id": 8, "name": "Farm"}])

        admin_cursor = FakeCursor([{"user_id": 1, "email": "admin@test"}])
        connect.return_value = FakeConnection(admin_cursor)
        admin = get_user_context("admin", 1)
        self.assertEqual(admin["farms"], [])
        self.assertEqual(admin["enterprises"], [])

    @patch("app.services.database._connect")
    def test_farm_data_is_bounded_and_serialized(self, connect) -> None:
        cursor = FakeCursor(
            [
                {"user_id": 42, "farm_id": 8, "enterprise_id": 3},
                [{"id": 8, "name": "Farm"}],
                [{"id": 1, "target_value": Decimal("4.5")}],
                [{"id": 2}],
                [{"id": 3}],
                [{"id": 4}],
                [{"id": 5}],
                [{"id": 6}],
                [{"id": 7}],
            ]
        )
        connect.return_value = FakeConnection(cursor)

        result = get_user_farm_data("farm_owner", 42, 10)

        self.assertEqual(result["farm_ids"], [8])
        self.assertEqual(result["data"]["individual_goals"][0]["target_value"], 4.5)

    @patch("app.services.database._connect")
    def test_farm_data_for_admin_has_no_farms(self, connect) -> None:
        connect.return_value = FakeConnection(
            FakeCursor([{"user_id": 1, "email": "admin@test"}])
        )

        self.assertEqual(
            get_user_farm_data("admin", 1),
            {
                "user_type": "admin",
                "user_id": 1,
                "farm_ids": [],
                "data": {},
            },
        )


if __name__ == "__main__":
    unittest.main()
