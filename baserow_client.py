# ============================================================
# Teacher Matching System V1
# baserow_client.py
#
# 负责：
# 1. 连接 Baserow
# 2. 读取 Teachers 表
# 3. 规范化 Baserow 字段值
# 4. 检查关键字段
# 5. 提供老师数据给匹配引擎
# ============================================================

from typing import Any, Dict, List, Optional

import requests

import config


# ============================================================
# 1. Baserow Configuration
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
        f"/api/database/rows/table/{TABLE_ID}/"
    )
else:
    BASEROW_TABLE_URL = None


if BASEROW_TOKEN:
    BASEROW_HEADERS = {
        "Authorization": f"Token {BASEROW_TOKEN}",
        "Content-Type": "application/json",
    }
else:
    BASEROW_HEADERS = {}


# ============================================================
# 2. Baserow Value Normalization
# ============================================================

def normalize_baserow_value(
    value: Any
) -> Any:
    """
    将 Baserow API 返回的数据转换成普通 Python 数据。

    Single Select:
    {
        "id": 123,
        "value": "United Kingdom"
    }

    转换为：

    "United Kingdom"

    Multiple Select:
    [
        {"id": 1, "value": "IB"},
        {"id": 2, "value": "A-Level"}
    ]

    转换为：

    ["IB", "A-Level"]
    """

    if isinstance(value, list):

        normalized_values = []

        for item in value:

            if isinstance(item, dict):

                option_value = item.get(
                    "value"
                )

                if option_value is not None:

                    normalized_values.append(
                        option_value
                    )

            elif item is not None:

                normalized_values.append(
                    item
                )

        return normalized_values

    if isinstance(value, dict):

        if "value" in value:
            return value.get(
                "value"
            )

        return value

    return value


# ============================================================
# 3. Number Conversion
# ============================================================

def to_number(
    value: Any
) -> Optional[float]:
    """
    安全转换成 float。
    """

    if value is None:
        return None

    if value == "":
        return None

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# 4. Boolean Conversion
# ============================================================

def to_boolean(
    value: Any
) -> bool:
    """
    将 Baserow Boolean / Checkbox 转成 bool。
    """

    if isinstance(
        value,
        bool,
    ):
        return value

    if value is None:
        return False

    normalized = (
        str(value)
        .strip()
        .lower()
    )

    if normalized in {
        "1",
        "true",
        "yes",
        "y",
    }:
        return True

    return False


# ============================================================
# 5. Field Groups
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
]


NUMBER_FIELDS = [
    "Years of Teaching",
    "Minimum Child Age",
    "Maximum Child Age",
]


# ============================================================
# 6. Normalize Teacher Record
# ============================================================

def normalize_teacher_record(
    row: Dict[str, Any]
) -> Dict[str, Any]:
    """
    将一条 Baserow Teacher row
    转换为系统统一格式。
    """

    teacher = {
        "Baserow ID": row.get(
            "id"
        )
    }

    for (
        field_name,
        raw_value,
    ) in row.items():

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

    # --------------------------------------------------------
    # Number fields
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # List fields
    # --------------------------------------------------------

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

            teacher[
                field_name
            ] = []

        else:

            teacher[
                field_name
            ] = [
                value
            ]

    # --------------------------------------------------------
    # Boolean fields
    # --------------------------------------------------------

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
# 7. Validate Teacher Record
# ============================================================

def validate_teacher_record(
    teacher: Dict[str, Any]
) -> List[str]:
    """
    检查老师资料是否缺少重要字段。
    """

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

    if not teacher.get(
        "Nationality"
    ):

        warnings.append(
            "缺少 Nationality"
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

    if not teacher.get(
        "Preferred Cities"
    ):

        warnings.append(
            "缺少 Preferred Cities"
        )

    if not teacher.get(
        "Visa / Work Authorization Countries"
    ):

        warnings.append(
            "缺少 Visa / Work Authorization Countries"
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
    """
    检查 Baserow 所需配置。
    """

    if not BASEROW_TOKEN:

        raise RuntimeError(
            "BASEROW_TOKEN 未配置。"
        )

    if TABLE_ID is None:

        raise RuntimeError(
            "TABLE_ID 未配置。"
        )

    if not BASEROW_TABLE_URL:

        raise RuntimeError(
            "无法生成 Baserow Table URL。"
        )


# ============================================================
# 9. Fetch Teacher Page
# ============================================================

def fetch_teacher_page(
    page: int = 1,
    size: int = BASEROW_PAGE_SIZE,
) -> Dict[str, Any]:
    """
    从 Baserow 读取一页 Teachers 数据。
    """

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
            f"HTTP 状态码：{response.status_code}\n"
            f"错误内容：{response.text}"
        )

    try:

        return response.json()

    except ValueError as error:

        raise RuntimeError(
            "Baserow 返回内容不是有效 JSON。"
        ) from error


# ============================================================
# 10. Load All Teachers
# ============================================================

def load_teachers(
    include_validation: bool = True,
) -> List[Dict[str, Any]]:
    """
    读取全部老师。

    自动处理 pagination。
    """

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

            # 跳过完全没有 First Name 的空白测试行
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

        next_page = payload.get(
            "next"
        )

        if not next_page:
            break

        page += 1

    return teachers


# ============================================================
# 11. Get Teacher by Baserow ID
# ============================================================

def get_teacher_by_id(
    teacher_id: int
) -> Optional[Dict[str, Any]]:
    """
    根据 Baserow ID 获取老师。
    """

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
# 12. Search Teacher by Name
# ============================================================

def search_teachers_by_name(
    query: str
) -> List[Dict[str, Any]]:
    """
    根据姓名搜索老师。
    """

    normalized_query = (
        str(query)
        .strip()
        .lower()
    )

    if not normalized_query:
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

        if (
            normalized_query
            in full_name
        ):

            results.append(
                teacher
            )

    return results


# ============================================================
# 13. Database Summary
# ============================================================

def get_teacher_database_summary() -> Dict[str, Any]:
    """
    返回老师数据库统计信息。
    """

    teachers = load_teachers()

    total_teachers = len(
        teachers
    )

    complete_age_range = 0
    with_preferred_cities = 0
    with_visa_countries = 0
    teachers_with_warnings = 0

    for teacher in teachers:

        if (
            teacher.get(
                "Minimum Child Age"
            )
            is not None
            and teacher.get(
                "Maximum Child Age"
            )
            is not None
        ):

            complete_age_range += 1

        if teacher.get(
            "Preferred Cities"
        ):

            with_preferred_cities += 1

        if teacher.get(
            "Visa / Work Authorization Countries"
        ):

            with_visa_countries += 1

        if teacher.get(
            "_validation_warnings"
        ):

            teachers_with_warnings += 1

    return {
        "total_teachers": (
            total_teachers
        ),

        "complete_age_range": (
            complete_age_range
        ),

        "with_preferred_cities": (
            with_preferred_cities
        ),

        "with_visa_countries": (
            with_visa_countries
        ),

        "teachers_with_warnings": (
            teachers_with_warnings
        ),
    }


# ============================================================
# 14. Baserow Health Check
# ============================================================

def check_baserow_connection() -> Dict[str, Any]:
    """
    测试 Baserow 连接。
    """

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
            "message": str(
                error
            ),
            "count": 0,
        }
