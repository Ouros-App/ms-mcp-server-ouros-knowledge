import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.config import settings
from app.core.identity import USER_TYPE_ERROR, VALID_USER_TYPES, UserType

DEFAULT_FARM_DATA_LIMIT = 20
MAX_FARM_DATA_LIMIT = 100
DEFAULT_CONSUMPTION_PERIOD_DAYS = 30
MAX_CONSUMPTION_PERIOD_DAYS = 366
USER_NOT_FOUND = "usuário não encontrado"


def _connect() -> psycopg.Connection:
    """Open a PostgreSQL connection using the configured read-only URL."""
    if not settings.MIDAS_DATABASE_URL:
        raise RuntimeError("MIDAS_DATABASE_URL não está configurada no .env")
    return psycopg.connect(
        settings.MIDAS_DATABASE_URL,
        connect_timeout=settings.MIDAS_DB_CONNECT_TIMEOUT,
        row_factory=dict_row,
    )


def _connect_import() -> psycopg.Connection:
    """Open the restricted database connection used only for imports."""
    if not settings.MIDAS_IMPORT_DATABASE_URL:
        raise RuntimeError("MIDAS_IMPORT_DATABASE_URL não está configurada no .env")
    return psycopg.connect(
        settings.MIDAS_IMPORT_DATABASE_URL,
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
        raise ValueError(USER_TYPE_ERROR)
    if user_id <= 0:
        raise ValueError("user_id deve ser maior que zero")


def _validate_limit(limit: int) -> None:
    """Validate the maximum number of records returned per collection."""
    if not 1 <= limit <= 100:
        raise ValueError("limit deve estar entre 1 e 100")


def _validate_period_days(period_days: int) -> None:
    """Bound aggregate queries to an integer read-only time window."""
    if (
        isinstance(period_days, bool)
        or not isinstance(period_days, int)
        or not 1 <= period_days <= MAX_CONSUMPTION_PERIOD_DAYS
    ):
        raise ValueError(
            "period_days deve ser um inteiro entre 1 e "
            f"{MAX_CONSUMPTION_PERIOD_DAYS}"
        )


def import_resource_records(
    user_type: UserType,
    user_id: int,
    request_id: str,
    source_type: str,
    source_name: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Submit a validated historical import through the PostgreSQL function only."""
    _validate_user(user_type, user_id)
    try:
        parsed_request_id = UUID(request_id)
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError("request_id deve ser um UUID válido") from error
    if not source_type.strip() or not source_name.strip():
        raise ValueError("source_type e source_name não podem ser vazios")
    if not isinstance(records, list) or len(records) > 1000:
        raise ValueError("records deve ser uma lista com no máximo 1000 itens")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("cada registro deve ser um objeto JSON")
    serialized_payload = json.dumps(records)
    if len(serialized_payload.encode("utf-8")) > 1024 * 1024:
        raise ValueError("payload de importação excede 1 MiB")
    payload = Jsonb(records, dumps=lambda _value: serialized_payload)

    with _connect_import() as connection:
        row = connection.execute(
            """
            SELECT midas.import_resource_records(
                %s, %s, %s, %s, %s, %s
            ) AS result
            """,
            (parsed_request_id, user_type, user_id, source_type.strip(),
             source_name.strip(), payload),
        ).fetchone()
    if not row or not isinstance(row["result"], dict):
        raise RuntimeError("função de importação retornou resposta inválida")
    return _json_safe(row["result"])


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
                fo.id_farm AS farm_id,
                f.id_enterprise AS enterprise_id
            FROM midas.farm_owners AS fo
            JOIN midas.farms AS f ON f.id = fo.id_farm
            WHERE fo.id = %s
            """,
            (user_id,),
        ).fetchone()
        if not row:
            raise ValueError(USER_NOT_FOUND)
        return dict(row), [row["farm_id"]], [row["enterprise_id"]]

    if user_type == "company_employee":
        row = cursor.execute(
            """
            SELECT
                ce.id AS user_id,
                ce.name,
                ce.id_enterprise AS enterprise_id
            FROM midas.company_employees AS ce
            WHERE ce.id = %s
            """,
            (user_id,),
        ).fetchone()
        if not row:
            raise ValueError(USER_NOT_FOUND)
        farms = cursor.execute(
            "SELECT id FROM midas.farms WHERE id_enterprise = %s",
            (row["enterprise_id"],),
        ).fetchall()
        return dict(row), [farm["id"] for farm in farms], [row["enterprise_id"]]

    row = cursor.execute(
        "SELECT id AS user_id FROM midas.adms WHERE id = %s",
        (user_id,),
    ).fetchone()
    if not row:
        raise ValueError(USER_NOT_FOUND)
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
                        SELECT name
                        FROM midas.enterprises
                        WHERE id = ANY(%s)
                        ORDER BY name
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
                            f.name,
                            f.area_property,
                            f.region,
                            f.poultry_capacity,
                            f.place,
                            a.state,
                            a.city
                        FROM midas.farms AS f
                        LEFT JOIN midas.addresses AS a ON a.id = f.id_address
                        WHERE f.id = ANY(%s)
                        ORDER BY f.id
                        """,
                    (farm_ids,),
                )
            )

    public_profile = {
        key: _json_safe(profile[key])
        for key in ("name",)
        if profile.get(key) is not None
    }
    return {
        "user_type": user_type,
        "profile": public_profile,
        "enterprises": enterprises,
        "farms": farms,
    }


def get_user_farm_data(
    user_type: UserType,
    user_id: int,
    limit: int = DEFAULT_FARM_DATA_LIMIT,
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
                        SELECT f.id, f.name, f.area_property, f.region,
                               f.poultry_capacity, f.place, f.id_address,
                               f.id_enterprise, a.state, a.city
                        FROM midas.farms AS f
                        LEFT JOIN midas.addresses AS a ON a.id = f.id_address
                        WHERE f.id = ANY(%s)
                        ORDER BY f.id
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
                               delivery_date, losts, cost, id_enterprise, id_farm
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


def get_consumption_summary(
    user_type: UserType,
    user_id: int,
    period_days: int = DEFAULT_CONSUMPTION_PERIOD_DAYS,
) -> dict[str, Any]:
    """Return scoped aggregate water/energy data without exposing arbitrary SQL."""
    _validate_user(user_type, user_id)
    _validate_period_days(period_days)

    with _connect() as connection, connection.cursor() as cursor:
        _, farm_ids, _ = _resolve_user_scope(cursor, user_type, user_id)
        if not farm_ids:
            return {
                "user_type": user_type,
                "user_id": user_id,
                "farm_ids": [],
                "period_days": period_days,
                "water_unit": "hydrometer_reading_delta",
                "energy_unit": "kWh",
                "summaries": [],
            }

        summaries = _rows(
            cursor.execute(
                """
                WITH water AS (
                    SELECT
                        id_farm,
                        COUNT(*) AS water_records,
                        MIN(registration_date) AS first_water_record,
                        MAX(registration_date) AS last_water_record,
                        SUM(end_hydrometer - start_hydrometer) AS water_meter_delta
                    FROM midas.water_registries
                    WHERE registration_date >= CURRENT_DATE - (%s - 1)
                      AND registration_date <= CURRENT_DATE
                      AND id_farm = ANY(%s)
                    GROUP BY id_farm
                ),
                energy AS (
                    SELECT
                        id_farm,
                        COUNT(*) AS energy_records,
                        MIN(registration_date) AS first_energy_record,
                        MAX(registration_date) AS last_energy_record,
                        SUM(energy_consumption) AS energy_consumption_kwh
                    FROM midas.energy_registries
                    WHERE registration_date >= CURRENT_DATE - (%s - 1)
                      AND registration_date <= CURRENT_DATE
                      AND id_farm = ANY(%s)
                    GROUP BY id_farm
                )
                SELECT
                    f.id AS id_farm,
                    f.name AS farm_name,
                    f.region,
                    f.place,
                    a.state,
                    a.city,
                    COALESCE(w.water_records, 0) AS water_records,
                    w.first_water_record,
                    w.last_water_record,
                    COALESCE(w.water_meter_delta, 0) AS water_meter_delta,
                    COALESCE(e.energy_records, 0) AS energy_records,
                    e.first_energy_record,
                    e.last_energy_record,
                    COALESCE(e.energy_consumption_kwh, 0) AS energy_consumption_kwh
                FROM midas.farms AS f
                LEFT JOIN midas.addresses AS a ON a.id = f.id_address
                LEFT JOIN water AS w ON w.id_farm = f.id
                LEFT JOIN energy AS e ON e.id_farm = f.id
                WHERE f.id = ANY(%s)
                ORDER BY f.id
                """,
                (period_days, farm_ids, period_days, farm_ids, farm_ids),
            )
        )

    return {
        "user_type": user_type,
        "user_id": user_id,
        "farm_ids": farm_ids,
        "period_days": period_days,
        "water_unit": "hydrometer_reading_delta",
        "energy_unit": "kWh",
        "summaries": summaries,
    }
