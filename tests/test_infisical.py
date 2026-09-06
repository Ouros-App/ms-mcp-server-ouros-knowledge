import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.infisical import load_infisical_secrets


class InfisicalTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_without_configuration_does_nothing(self) -> None:
        with patch("app.core.infisical.InfisicalSDKClient") as client:
            load_infisical_secrets()
        client.assert_not_called()

    @patch.dict(os.environ, {"INFISICAL_TOKEN": "token"}, clear=True)
    def test_partial_configuration_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "devem ser configurados juntos"):
            load_infisical_secrets()

    @patch.dict(
        os.environ,
        {
            "INFISICAL_TOKEN": "token",
            "INFISICAL_PROJECT_ID": "project",
            "INFISICAL_ENV": "dev",
            "INFISICAL_PATH": "/app",
        },
        clear=True,
    )
    def test_loads_secrets_into_environment(self) -> None:
        client = SimpleNamespace(
            secrets=SimpleNamespace(
                list_secrets=lambda **_kwargs: SimpleNamespace(
                    secrets=[SimpleNamespace(secretKey="APP_SECRET", secretValue="ok")]
                )
            )
        )
        with patch("app.core.infisical.InfisicalSDKClient", return_value=client):
            load_infisical_secrets()
        self.assertEqual(os.environ["APP_SECRET"], "ok")
