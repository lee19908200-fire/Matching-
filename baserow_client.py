# ============================================================
# Teacher Matching System V1.1
# baserow_client.py
# ============================================================

from typing import Any, Dict, List, Optional

import requests

import config


# ============================================================
# 1. Configuration
# ============================================================

BASEROW_TOKEN = getattr(
    config,
    "BASEROW_TOKEN",
    None,
)

TABLE_ID = getattr(
    config,
    "TABLE_ID",
    None,
)

BASEROW_PAGE_SIZE = getattr(
    config,
    "BASEROW_PAGE_SIZE",
    200,
)

REQUEST_TIMEOUT = getattr(
    config,
    "REQUEST_TIMEOUT",
    30,
)


if TABLE_ID is not None:

    BASEROW_TABLE_URL = (
        "https://api.baserow.io"
        f"/api/database/rows/table/"
        f"{TABLE_ID}/"
    )

else:

    BASEROW_TABLE_URL = None


if BASEROW_TOKEN:

    BASEROW_HEADERS = {
        "Authorization": (
            f"Token {BASEROW_TOKEN}"
        ),
        "Content-Type": (
            "application/json"
        ),
    }

else:

    BASEROW_HEADERS = {}


# ============================================================
# 2. Field Types
# ============================================================

LIST_FIELDS = [
    "Subjects",
    "Age Groups",
    "Curriculum",
    "Teaching Languages",
    "Desired Position",
    "Preferred Cities",
    "Visa / Work Authorization Countries",
]


BOOLEAN_FIELDS = [
    "SEN Experience",
    "International School Experience",
    "Private Tutoring Experience",
    "Live-in",
    "Willing to Travel",
    "Driving",
    "Governor/Governess Experience",
    "Nanny Educator Experience",
    "Night Care",
    "Private Room Required",
]


NUMBER_FIELDS = [
    "Age",
    "Years of Teaching",
    "Minimum Child Age",
    "Maximum Child Age",
]


# ============================================================
# 3. Normalize Baserow Values
# ============================================================

def normalize_baserow_value(
    value: Any
) -> Any:

    if isinstance(value, list):

        result = []

        for item in value:

            if isinstance(item, dict):

                if "value" in item:

                    result.append(
                        item["value"]
                    )

            elif item is not None:

                result.append(
                    item
                )

        return result

    if isinstance(value, dict):

        if "value" in value:
            return value["value"]

        return value

    return value


# ============================================================
# 4. Number
# ============================================================

def to_number(
    value: Any
) -> Optional[float]:

    if value is None:
        return None

    if value == "":
        return None

    try:

        return float(value)

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# 5. Boolean
# ============================================================

def to_boolean(
    value: Any
) -> bool:

    if isinstance(
        value,
        bool,
    ):

        return value

    if value is None:
        return False

    text = (
        str(value)
        .strip()
        .lower()
    )

    return text in {
        "1",
        "true",
        "yes",
        "y",
    }


# ============================================================
# 6. Normalize Teacher
# ============================================================

def normalize_teacher_record(
    row: Dict[str, Any]
) -> Dict[str, Any]:

    teacher = {
        "Baserow ID": row.get(
            "id"
        )
    }

    for field_name, raw_value in row.items():

        if field_name in {
            "id",
            "order",
        }:
            continue

        teacher[field_name] = (
            normalize_baserow_value(
                raw_value
            )
        )

    # Numbers
    for field_name in NUMBER_FIELDS:

        teacher[field_name] = (
            to_number(
                teacher.get(
                    field_name
                )
            )
        )

    if (
        teacher.get(
            "Years of Teaching"
        )
        is None
    ):

        teacher[
            "Years of Teaching"
        ] = 0.0

    # Lists
    for field_name in LIST_FIELDS:

        value = teacher.get(
            field_name
        )

        if isinstance(
            value,
            list,
        ):

            continue

        if value is None:

            teacher[field_name] = []

        else:

            teacher[field_name] = [
                value
            ]

    # Boolean
    for field_name in BOOLEAN_FIELDS:

        teacher[field_name] = (
            to_boolean(
                teacher.get(
                    field_name
                )
            )
        )

    return teacher


# ============================================================
# 7. Validate Teacher
# ============================================================

def validate_teacher_record(
    teacher: Dict[str, Any]
) -> List[str]:

    warnings = []

    if not teacher.get(
        "First Name"
    ):

        warnings.append(
            "缺少 First Name"
        )

    if not teacher.get(
        "Last Name"
    ):

        warnings.append(
            "缺少 Last Name"
        )

    if teacher.get(
        "Age"
    ) is None:

        warnings.append(
            "缺少 Age"
        )

    if not teacher.get(
        "Nationality"
    ):

        warnings.append(
            "缺少 Nationality"
        )

    if not teacher.get(
        "Preferred Cities"
    ):

        warnings.append(
            "缺少 Preferred Cities"
        )

    if (
        teacher.get(
            "Minimum Child Age"
        )
        is None
    ):

        warnings.append(
            "缺少 Minimum Child Age"
        )

    if (
        teacher.get(
            "Maximum Child Age"
        )
        is None
    ):

        warnings.append(
            "缺少 Maximum Child Age"
        )

    minimum_age = teacher.get(
        "Minimum Child Age"
    )

    maximum_age = teacher.get(
        "Maximum Child Age"
    )

    if (
        minimum_age is not None
        and maximum_age is not None
        and minimum_age > maximum_age
    ):

        warnings.append(
            "Minimum Child Age 大于 Maximum Child Age"
        )

    return warnings


# ============================================================
# 8. Configuration Check
# ============================================================

def validate_baserow_configuration():

    if not BASEROW_TOKEN:

        raise RuntimeError(
            "BASEROW_TOKEN 未配置。"
        )

    if TABLE_ID is None:

        raise RuntimeError(
            "TABLE_ID 未配置。"
        )


# ============================================================
# 9. Fetch Page
# ============================================================

def fetch_teacher_page(
    page: int = 1,
    size: int = BASEROW_PAGE_SIZE,
) -> Dict[str, Any]:

    validate_baserow_configuration()

    response = requests.get(
        BASEROW_TABLE_URL,
        headers=BASEROW_HEADERS,
        params={
            "page": page,
            "size": size,
            "user_field_names": "true",
        },
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code != 200:

        raise RuntimeError(
            "读取 Baserow Teachers 失败。\n"
            f"HTTP：{response.status_code}\n"
            f"{response.text}"
        )

    return response.json()


# ============================================================
# 10. Load Teachers
# ============================================================

def load_teachers(
    include_validation: bool = True,
) -> List[Dict[str, Any]]:

    teachers = []

    page = 1

    while True:

        payload = fetch_teacher_page(
            page=page,
            size=BASEROW_PAGE_SIZE,
        )

        rows = payload.get(
            "results",
            [],
        )

        for row in rows:

            teacher = (
                normalize_teacher_record(
                    row
                )
            )

            if not teacher.get(
                "First Name"
            ):
                continue

            if include_validation:

                teacher[
                    "_validation_warnings"
                ] = (
                    validate_teacher_record(
                        teacher
                    )
                )

            teachers.append(
                teacher
            )

        if not payload.get(
            "next"
        ):
            break

        page += 1

    return teachers


# ============================================================
# 11. Get Teacher by ID
# ============================================================

def get_teacher_by_id(
    teacher_id: int
) -> Optional[Dict[str, Any]]:

    teachers = load_teachers()

    for teacher in teachers:

        if (
            teacher.get(
                "Baserow ID"
            )
            ==
            teacher_id
        ):

            return teacher

    return None


# ============================================================
# 12. Search Teachers
# ============================================================

def search_teachers_by_name(
    query: str
) -> List[Dict[str, Any]]:

    query = (
        str(query)
        .strip()
        .lower()
    )

    if not query:
        return []

    teachers = load_teachers()

    results = []

    for teacher in teachers:

        first_name = str(
            teacher.get(
                "First Name"
            )
            or ""
        )

        last_name = str(
            teacher.get(
                "Last Name"
            )
            or ""
        )

        full_name = (
            f"{first_name} {last_name}"
            .strip()
            .lower()
        )

        if query in full_name:

            results.append(
                teacher
            )

    return results


# ============================================================
# 13. Health Check
# ============================================================

def check_baserow_connection():

    try:

        payload = fetch_teacher_page(
            page=1,
            size=1,
        )

        return {
            "success": True,
            "message": (
                "Baserow 连接正常"
            ),
            "count": payload.get(
                "count",
                0,
            ),
        }

    except Exception as error:

        return {
            "success": False,
            "message": str(error),
            "count": 0,
        }
