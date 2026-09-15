import os

from dotenv import load_dotenv
from infisical_sdk import InfisicalSDKClient


def load_infisical_secrets() -> None:
    load_dotenv()
    token = os.getenv("INFISICAL_TOKEN")
    client_id = os.getenv("INFISICAL_CLIENT_ID")
    client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
    project_id = os.getenv("INFISICAL_PROJECT_ID")
    environment = os.getenv("INFISICAL_ENV") or os.getenv("INFISICAL_ENVIRONMENT")
    secret_path = os.getenv("INFISICAL_PATH") or os.getenv("INFISICAL_SECRET_PATH")
    host = os.getenv("INFISICAL_HOST") or os.getenv("INFISICAL_SITE_URL", "https://app.infisical.com")
    if not any((token, client_id, client_secret, project_id, environment, secret_path)):
        return
    if not all((project_id, environment, secret_path)) or not (token or all((client_id, client_secret))):
        raise RuntimeError(
            "As credenciais, projeto, ambiente e caminho do Infisical devem ser configurados juntos"
        )
    client = InfisicalSDKClient(host=host, token=token)
    if not token:
        client.auth.universal_auth.login(client_id=client_id, client_secret=client_secret)
    response = client.secrets.list_secrets(
        project_id=project_id,
        environment_slug=environment,
        secret_path=secret_path,
        view_secret_value=True,
    )
    for secret in response.secrets:
        os.environ[secret.secretKey] = secret.secretValue
