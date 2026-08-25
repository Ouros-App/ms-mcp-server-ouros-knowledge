from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings

UserType = Literal["farm_owner", "company_employee", "admin"]
VALID_USER_TYPES = {"farm_owner", "company_employee", "admin"}


def _connect() -> psycopg.Connection:
    """Open a PostgreSQL connection using the configured read-only URL."""
    if not settings.MIDAS_DATABASE_URL:
        raise RuntimeError("MIDAS_DATABASE_URL não está configurada no .env")
    return psycopg.connect(
        settings.MIDAS_DATABASE_URL,
        connect_timeout=settings.MIDAS_DB_CONNECT_TIMEOUT,
        row_factory=dict_row,
    )


def _json_safe(value: Any) -> Any:
    """Convert PostgreSQL values into JSON-compatible primitives."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _rows(cursor: Any) -> list[dict[str, Any]]:
    """Fetch cursor rows as sanitized dictionaries."""
    return [_json_safe(dict(row)) for row in cursor.fetchall()]


def _validate_user(user_type: str, user_id: int) -> None:
    """Validate the supported user identity shape."""
    if user_type not in VALID_USER_TYPES:
        raise ValueError("user_type deve ser farm_owner, company_employee ou admin")
    if user_id <= 0:
        raise ValueError("user_id deve ser maior que zero")


def _validate_limit(limit: int) -> None:
    """Validate the maximum number of records returned per collection."""
    if not 1 <= limit <= 100:
        raise ValueError("limit deve estar entre 1 e 100")


def _resolve_user_scope(
    cursor: Any,
    user_type: UserType,
    user_id: int,
) -> tuple[dict[str, Any], list[int], list[int]]:
    """Resolve a user and the farms and enterprises they may access."""
    if user_type == "farm_owner":
        row = cursor.execute(
            """
            SELECT
                fo.id AS user_id,
                fo.name,
                fo.email,
                fo.document_number,
                fo.telephone,
                fo.id_farm AS farm_id,
                f.id_enterprise AS enterprise_id
            FROM midas.farm_owners AS fo
            JOIN midas.farms AS f ON f.id = fo.id_farm
            WHERE fo.id = %s
            """,
            (user_id,),
        ).fetchone()
        if not row:
            raise ValueError("usuário não encontrado")
        return dict(row), [row["farm_id"]], [row["enterprise_id"]]

    if user_type == "company_employee":
        row = cursor.execute(
            """
            SELECT
                ce.id AS user_id,
                ce.name,
                ce.document_number,
                ce.email,
                ce.telephone,
                ce.id_enterprise AS enterprise_id
            FROM midas.company_employees AS ce
            WHERE ce.id = %s
            """,
            (user_id,),
        ).fetchone()
        if not row:
            raise ValueError("usuário não encontrado")
        farms = cursor.execute(
            "SELECT id FROM midas.farms WHERE id_enterprise = %s",
            (row["enterprise_id"],),
        ).fetchall()
        return dict(row), [farm["id"] for farm in farms], [row["enterprise_id"]]

    row = cursor.execute(
        "SELECT id AS user_id, email FROM midas.adms WHERE id = %s",
        (user_id,),
    ).fetchone()
    if not row:
        raise ValueError("usuário não encontrado")
    return dict(row), [], []


def postgres_status() -> dict[str, Any]:
    """Check the configured read-only PostgreSQL connection."""
    try:
        with _connect() as connection:
            row = connection.execute(
                "SELECT current_database() AS database, current_user AS user"
            ).fetchone()
        return {
            "connected": True,
            "database": row["database"],
            "user": row["user"],
        }
    except Exception as error:  # noqa: BLE001 - status must report network failures safely
        return {"connected": False, "error": type(error).__name__}


def get_user_context(user_type: UserType, user_id: int) -> dict[str, Any]:
    """Return the authenticated application's user profile and linked farms."""
    _validate_user(user_type, user_id)

    with _connect() as connection, connection.cursor() as cursor:
        profile, farm_ids, enterprise_ids = _resolve_user_scope(
            cursor, user_type, user_id
        )
        enterprises = []
        if enterprise_ids:
            enterprises = _rows(
                cursor.execute(
                    """
                        SELECT id, name, email, document_number, telephone, id_address
                        FROM midas.enterprises
                        WHERE id = ANY(%s)
                        ORDER BY id
                        """,
                    (enterprise_ids,),
                )
            )
        farms = []
        if farm_ids:
            farms = _rows(
                cursor.execute(
                    """
                        SELECT
                            id,
                            name,
                            area_property,
                            region,
                            poultry_capacity,
                            place,
                            id_address,
                            id_enterprise
                        FROM midas.farms
                        WHERE id = ANY(%s)
                        ORDER BY id
                        """,
                    (farm_ids,),
                )
            )

    return {
        "user_type": user_type,
        "user_id": user_id,
        "profile": _json_safe(profile),
        "enterprises": enterprises,
        "farms": farms,
    }


def get_user_farm_data(
    user_type: UserType, user_id: int, limit: int = 20
) -> dict[str, Any]:
    """Return bounded farm records scoped to the user's linked farms."""
    _validate_user(user_type, user_id)
    _validate_limit(limit)

    with _connect() as connection, connection.cursor() as cursor:
        _, farm_ids, _ = _resolve_user_scope(cursor, user_type, user_id)
        if not farm_ids:
            return {
                "user_type": user_type,
                "user_id": user_id,
                "farm_ids": [],
                "data": {},
            }

        data = {
            "farms": _rows(
                cursor.execute(
                    """
                        SELECT id, name, area_property, region,
                               poultry_capacity, place, id_address, id_enterprise
                        FROM midas.farms
                        WHERE id = ANY(%s)
                        ORDER BY id
                        LIMIT %s
                        """,
                    (farm_ids, limit),
                )
            ),
            "individual_goals": _rows(
                cursor.execute(
                    """
                        SELECT id, description, type, status, target_value,
                               title, id_farm
                        FROM midas.individual_goals
                        WHERE id_farm = ANY(%s)
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                    (farm_ids, limit),
                )
            ),
            "state_goals": _rows(
                cursor.execute(
                    """
                        SELECT id, description, type, status, target_value,
                               title, date_creation, date_end, id_farm
                        FROM midas.state_goals
                        WHERE id_farm = ANY(%s)
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                    (farm_ids, limit),
                )
            ),
            "water_registries": _rows(
                cursor.execute(
                    """
                        SELECT id, registration_date, start_hydrometer,
                               end_hydrometer, id_farm
                        FROM midas.water_registries
                        WHERE id_farm = ANY(%s)
                        ORDER BY registration_date DESC, id DESC
                        LIMIT %s
                        """,
                    (farm_ids, limit),
                )
            ),
            "energy_registries": _rows(
                cursor.execute(
                    """
                        SELECT id, registration_date, energy_consumption, id_farm
                        FROM midas.energy_registries
                        WHERE id_farm = ANY(%s)
                        ORDER BY registration_date DESC, id DESC
                        LIMIT %s
                        """,
                    (farm_ids, limit),
                )
            ),
            "lots": _rows(
                cursor.execute(
                    """
                        SELECT id, received_chickens, delivered_chickens,
                               date_birth, delivery_date, gain, id_enterprise, id_farm
                        FROM midas.lots
                        WHERE id_farm = ANY(%s)
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                    (farm_ids, limit),
                )
            ),
            "tips": _rows(
                cursor.execute(
                    """
                        SELECT id, tip, id_farm
                        FROM midas.tips
                        WHERE id_farm = ANY(%s)
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                    (farm_ids, limit),
                )
            ),
        }

    return {
        "user_type": user_type,
        "user_id": user_id,
        "farm_ids": farm_ids,
        "data": data,
    }
