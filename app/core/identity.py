from typing import Literal, get_args

FARM_OWNER_USER_TYPE = "farm_owner"
COMPANY_EMPLOYEE_USER_TYPE = "company_employee"
ADMIN_USER_TYPE = "admin"

UserType = Literal[
    "farm_owner",
    "company_employee",
    "admin",
]
USER_TYPES = get_args(UserType)
VALID_USER_TYPES = frozenset(USER_TYPES)
USER_TYPE_ERROR = "user_type deve ser " + ", ".join(USER_TYPES[:-1]) + " ou " + USER_TYPES[-1]
