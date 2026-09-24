from typing import Literal, get_args

UserType = Literal["farm_owner", "company_employee", "admin"]
VALID_USER_TYPES = frozenset(get_args(UserType))
USER_TYPE_ERROR = "user_type deve ser farm_owner, company_employee ou admin"
