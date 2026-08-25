import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app.services.database import _json_safe, get_user_context, get_user_farm_data


class DatabaseGuardTests(unittest.TestCase):
    def test_json_safe_converts_postgres_values(self) -> None:
        value = _json_safe({"date": date(2026, 8, 25), "amount": Decimal("1.5")})

        self.assertEqual(value, {"date": "2026-08-25", "amount": 1.5})

    @patch("app.services.database._connect")
    def test_invalid_user_does_not_open_database_connection(self, connect) -> None:
        with self.assertRaises(ValueError):
            get_user_context("unknown", 1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            get_user_farm_data("farm_owner", 0)

        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
