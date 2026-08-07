# ============================================================
# Teacher Matching System V1
# matcher.py
#
# 负责：
# 1. 匹配单个老师
# 2. 计算硬条件和偏好条件
# 3. 计算 Match Score
# 4. 排序 Top Candidates
# 5. 生成基础推荐理由
# ============================================================

from typing import Any, Dict, List, Optional

from config import (
    BOOLEAN_FIELDS,
    HARD_REQUIREMENT_WEIGHT,
    MULTI_SELECT_FIELDS,
    PREFERRED_REQUIREMENT_WEIGHT,
    TOP_N,
)


# ============================================================
# 1. General Helpers
# ============================================================

def ensure_list(
    value: Any
) -> List[Any]:
    """
    将单个值统一转换成 list。
    """

    if value is None:
        return []

    if isinstance(
        value,
        list,
    ):
        return value

    return [
        value
    ]


def normalize_text(
    value: Any
) -> str:
    """
    文本统一：
    - strip
    - lower
    """

    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .lower()
    )


def to_number(
    value: Any
) -> Optional[float]:
    """
    安全地转换数字。
    """

    if value is None:
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
# 2. Exact Text Match
# ============================================================

def match_exact_text(
    actual: Any,
    expected: Any,
) -> bool:
    """
    不区分大小写的文本精确匹配。
    """

    return (
        normalize_text(
            actual
        )
        ==
        normalize_text(
            expected
        )
    )


# ============================================================
# 3. Multiple Select Match
# ============================================================

def match_multiple_select(
    actual: Any,
    expected: Any,
    mode: str = "all",
) -> bool:
    """
    多选字段匹配。

    mode="all"
    老师必须包含全部要求。

    mode="any"
    老师包含任意一个即可。
    """

    actual_values = {
        normalize_text(
            item
        )
        for item in ensure_list(
            actual
        )
        if item is not None
    }

    expected_values = {
        normalize_text(
            item
        )
        for item in ensure_list(
            expected
        )
        if item is not None
    }

    if not expected_values:
        return True

    if mode == "any":
        return bool(
            actual_values.intersection(
                expected_values
            )
        )

    return (
        expected_values
        .issubset(
            actual_values
        )
    )


# ============================================================
# 4. Boolean Match
# ============================================================

def match_boolean(
    actual: Any,
    expected: Any,
) -> bool:
    """
    Checkbox / Boolean 匹配。
    """

    return (
        bool(actual)
        is
        bool(expected)
    )


# ============================================================
# 5. Working City Match
# ============================================================

def match_working_city(
    teacher: Dict[str, Any],
    working_city: Any,
) -> bool:
    """
    工作城市匹配。

    比较：
    雇主 Working City
    VS
    老师 Preferred Cities

    如果老师 Preferred Cities 中包含 Any City，
    自动视为匹配任何城市。
    """

    if working_city is None:
        return True

    required_city = (
        normalize_text(
            working_city
        )
    )

    preferred_cities = (
        teacher.get(
            "Preferred Cities"
        )
        or []
    )

    normalized_cities = {
        normalize_text(
            city
        )
        for city in preferred_cities
    }

    if (
        normalize_text(
            "Any City"
        )
        in normalized_cities
    ):
        return True

    return (
        required_city
        in
        normalized_cities
    )


# ============================================================
# 6. Child Age Match
# ============================================================

def match_child_age(
    teacher: Dict[str, Any],
    child_age: Any,
) -> bool:
    """
    判断客户孩子年龄是否在老师接受范围内。

    Teacher:
    Minimum Child Age
    Maximum Child Age

    Requirement:
    Child Age
    """

    required_age = (
        to_number(
            child_age
        )
    )

    minimum_age = (
        to_number(
            teacher.get(
                "Minimum Child Age"
            )
        )
    )

    maximum_age = (
        to_number(
            teacher.get(
                "Maximum Child Age"
            )
        )
    )

    if (
        required_age
        is None
    ):
        return False

    if (
        minimum_age
        is None
        or maximum_age
        is None
    ):
        return False

    return (
        minimum_age
        <= required_age
        <= maximum_age
    )


# ============================================================
# 7. Minimum Teaching Years Match
# ============================================================

def match_minimum_years(
    teacher: Dict[str, Any],
    minimum_years: Any,
) -> bool:
    """
    老师教学经验是否达到最低年限。
    """

    required_years = (
        to_number(
            minimum_years
        )
    )

    actual_years = (
        to_number(
            teacher.get(
                "Years of Teaching"
            )
        )
    )

    if (
        required_years
        is None
    ):
        return False

    if (
        actual_years
        is None
    ):
        return False

    return (
        actual_years
        >=
        required_years
    )


# ============================================================
# 8. Generic Field Match
# ============================================================

def match_field(
    teacher: Dict[str, Any],
    field: str,
    expected: Any,
    multi_select_mode: str = "all",
) -> bool:
    """
    根据字段类型自动匹配。
    """

    # --------------------------------------------------------
    # Working City
    # --------------------------------------------------------

    if (
        field
        ==
        "Working City"
    ):
        return (
            match_working_city(
                teacher,
                expected,
            )
        )

    # --------------------------------------------------------
    # Child Age
    # --------------------------------------------------------

    if (
        field
        ==
        "Child Age"
    ):
        return (
            match_child_age(
                teacher,
                expected,
            )
        )

    # --------------------------------------------------------
    # Minimum Years
    # --------------------------------------------------------

    if (
        field
        ==
        "Minimum Years of Teaching"
    ):
        return (
            match_minimum_years(
                teacher,
                expected,
            )
        )

    # --------------------------------------------------------
    # Multiple Select
    # --------------------------------------------------------

    if (
        field
        in
        MULTI_SELECT_FIELDS
    ):
        return (
            match_multiple_select(
                teacher.get(
                    field
                ),
                expected,
                mode=(
                    multi_select_mode
                ),
            )
        )

    # --------------------------------------------------------
    # Boolean
    # --------------------------------------------------------

    if (
        field
        in
        BOOLEAN_FIELDS
    ):
        return (
            match_boolean(
                teacher.get(
                    field
                ),
                expected,
            )
        )

    # --------------------------------------------------------
    # Exact Text
    # --------------------------------------------------------

    return (
        match_exact_text(
            teacher.get(
                field
            ),
            expected,
        )
    )


# ============================================================
# 9. Evaluate Requirement Group
# ============================================================

def evaluate_requirements(
    teacher: Dict[str, Any],
    requirements: Dict[str, Any],
    multi_select_mode: str = "all",
) -> Dict[str, List[str]]:
    """
    检查一组 requirements。

    返回：

    matched
    missing
    """

    matched = []

    missing = []

    for (
        field,
        expected
    ) in requirements.items():

        if value_is_empty(
            expected
        ):
            continue

        is_match = (
            match_field(
                teacher=teacher,
                field=field,
                expected=expected,
                multi_select_mode=(
                    multi_select_mode
                ),
            )
        )

        if is_match:
            matched.append(
                field
            )

        else:
            missing.append(
                field
            )

    return {
        "matched": matched,
        "missing": missing,
    }


# ============================================================
# 10. Empty Value Helper
# ============================================================

def value_is_empty(
    value: Any
) -> bool:
    """
    判断 requirement 是否为空。
    """

    if value is None:
        return True

    if value == "":
        return True

    if value == []:
        return True

    return False


# ============================================================
# 11. Match Score
# ============================================================

def calculate_match_score(
    hard_matched: int,
    hard_total: int,
    preferred_matched: int,
    preferred_total: int,
) -> int:
    """
    综合评分：

    硬条件默认 80%
    偏好条件默认 20%
    """

    if hard_total:
        hard_score = (
            hard_matched
            /
            hard_total
        )

    else:
        hard_score = 1.0

    if preferred_total:
        preferred_score = (
            preferred_matched
            /
            preferred_total
        )

    else:
        preferred_score = 1.0

    total_score = (
        hard_score
        *
        HARD_REQUIREMENT_WEIGHT
        +
        preferred_score
        *
        PREFERRED_REQUIREMENT_WEIGHT
    )

    return round(
        total_score
        *
        100
    )


# ============================================================
# 12. Teacher Name
# ============================================================

def get_teacher_name(
    teacher: Dict[str, Any]
) -> str:
    """
    拼接老师姓名。
    """

    first_name = (
        teacher.get(
            "First Name"
        )
        or ""
    )

    last_name = (
        teacher.get(
            "Last Name"
        )
        or ""
    )

    full_name = (
        f"{first_name} "
        f"{last_name}"
    ).strip()

    if full_name:
        return full_name

    return (
        f"Teacher "
        f'{teacher.get("Baserow ID", "")}'
    )


# ============================================================
# 13. Human Friendly Labels
# ============================================================

FIELD_LABELS = {
    "Nationality": "国籍",
    "Current Country": "当前国家",
    "Visa Status": "签证状态",
    "Visa / Work Authorization Countries": (
        "签证/合法工作国家"
    ),
    "Highest Degree": "最高学历",
    "Minimum Years of Teaching": "最低教学年限",
    "Child Age": "孩子年龄",
    "Working City": "工作城市",
    "Subjects": "学科",
    "Curriculum": "课程体系",
    "Teaching Languages": "教学语言",
    "SEN Experience": "SEN经验",
    "International School Experience": (
        "国际学校经验"
    ),
    "Private Tutoring Experience": (
        "私人辅导经验"
    ),
    "Live-in": "住家",
    "Willing to Travel": "愿意旅行",
    "Driving": "驾驶",
    "Nanny Educator Experience": (
        "育儿教育经验"
    ),
}


def get_field_label(
    field: str
) -> str:
    """
    返回中文显示名称。
    """

    return (
        FIELD_LABELS.get(
            field,
            field,
        )
    )


# ============================================================
# 14. Describe Matched Requirement
# ============================================================

def describe_requirement(
    field: str,
    expected: Any,
) -> str:
    """
    把 requirement 转成适合界面显示的文字。
    """

    label = (
        get_field_label(
            field
        )
    )

    if isinstance(
        expected,
        list,
    ):
        value_text = (
            ", ".join(
                str(item)
                for item in expected
            )
        )

    elif isinstance(
        expected,
        bool,
    ):
        value_text = (
            "是"
            if expected
            else "否"
        )

    else:
        value_text = str(
            expected
        )

    return (
        f"{label}: "
        f"{value_text}"
    )


# ============================================================
# 15. Generate Recommendation Reasons
# ============================================================

def generate_recommendation_reasons(
    teacher: Dict[str, Any],
    hard_requirements: Dict[str, Any],
    preferred_requirements: Dict[str, Any],
    hard_matched: List[str],
    preferred_matched: List[str],
) -> List[str]:
    """
    生成基础版推荐理由。

    V1 不再调用第二次 Gemini，
    先使用结构化理由，减少 API 成本。
    """

    reasons = []

    # --------------------------------------------------------
    # Hard matched
    # --------------------------------------------------------

    for field in hard_matched:

        expected = (
            hard_requirements.get(
                field
            )
        )

        reasons.append(
            describe_requirement(
                field,
                expected,
            )
        )

    # --------------------------------------------------------
    # Preferred matched
    # --------------------------------------------------------

    for field in preferred_matched:

        expected = (
            preferred_requirements.get(
                field
            )
        )

        reasons.append(
            "偏好匹配 — "
            +
            describe_requirement(
                field,
                expected,
            )
        )

    # --------------------------------------------------------
    # Teaching experience
    # --------------------------------------------------------

    years = (
        teacher.get(
            "Years of Teaching"
        )
    )

    if years is not None:

        try:
            number_years = (
                float(
                    years
                )
            )

            if (
                number_years
                >= 10
            ):
                reasons.append(
                    "拥有10年以上教学经验"
                )

            elif (
                number_years
                >= 5
            ):
                reasons.append(
                    "拥有5年以上教学经验"
                )

        except (
            TypeError,
            ValueError,
        ):
            pass

    # --------------------------------------------------------
    # International school
    # --------------------------------------------------------

    if teacher.get(
        "International School Experience"
    ):
        reasons.append(
            "具有国际学校经验"
        )

    # --------------------------------------------------------
    # Private tutoring
    # --------------------------------------------------------

    if teacher.get(
        "Private Tutoring Experience"
    ):
        reasons.append(
            "具有私人辅导经验"
        )

    # 去重
    unique_reasons = []

    for reason in reasons:

        if (
            reason
            not in
            unique_reasons
        ):
            unique_reasons.append(
                reason
            )

    return (
        unique_reasons[:8]
    )


# ============================================================
# 16. Match One Teacher
# ============================================================

def match_teacher(
    teacher: Dict[str, Any],
    hard_requirements: Dict[str, Any],
    preferred_requirements: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:
    """
    匹配一位老师。
    """

    if preferred_requirements is None:
        preferred_requirements = {}

    # --------------------------------------------------------
    # Hard requirements
    # --------------------------------------------------------

    hard_result = (
        evaluate_requirements(
            teacher=teacher,
            requirements=(
                hard_requirements
            ),
            multi_select_mode="all",
        )
    )

    # --------------------------------------------------------
    # Preferred requirements
    # --------------------------------------------------------

    preferred_result = (
        evaluate_requirements(
            teacher=teacher,
            requirements=(
                preferred_requirements
            ),
            multi_select_mode="any",
        )
    )

    hard_total = (
        len(
            hard_result[
                "matched"
            ]
        )
        +
        len(
            hard_result[
                "missing"
            ]
        )
    )

    preferred_total = (
        len(
            preferred_result[
                "matched"
            ]
        )
        +
        len(
            preferred_result[
                "missing"
            ]
        )
    )

    score = (
        calculate_match_score(
            hard_matched=len(
                hard_result[
                    "matched"
                ]
            ),
            hard_total=(
                hard_total
            ),
            preferred_matched=len(
                preferred_result[
                    "matched"
                ]
            ),
            preferred_total=(
                preferred_total
            ),
        )
    )

    eligible = (
        len(
            hard_result[
                "missing"
            ]
        )
        ==
        0
    )

    reasons = (
        generate_recommendation_reasons(
            teacher=teacher,
            hard_requirements=(
                hard_requirements
            ),
            preferred_requirements=(
                preferred_requirements
            ),
            hard_matched=(
                hard_result[
                    "matched"
                ]
            ),
            preferred_matched=(
                preferred_result[
                    "matched"
                ]
            ),
        )
    )

    return {
        "teacher": teacher,

        "teacher_id": (
            teacher.get(
                "Baserow ID"
            )
        ),

        "name": (
            get_teacher_name(
                teacher
            )
        ),

        "score": score,

        "eligible": (
            eligible
        ),

        "hard_matched": (
            hard_result[
                "matched"
            ]
        ),

        "hard_missing": (
            hard_result[
                "missing"
            ]
        ),

        "preferred_matched": (
            preferred_result[
                "matched"
            ]
        ),

        "preferred_missing": (
            preferred_result[
                "missing"
            ]
        ),

        "recommendation_reasons": (
            reasons
        ),
    }


# ============================================================
# 17. Sort Results
# ============================================================

def sort_matching_results(
    results: List[
        Dict[str, Any]
    ]
) -> List[
    Dict[str, Any]
]:
    """
    排序规则：

    1. Eligible 优先
    2. Score 高优先
    3. Teaching Years 高优先
    """

    sorted_results = sorted(
        results,
        key=lambda result: (
            result.get(
                "eligible",
                False
            ),

            result.get(
                "score",
                0
            ),

            to_number(
                result.get(
                    "teacher",
                    {}
                ).get(
                    "Years of Teaching"
                )
            )
            or 0,
        ),
        reverse=True,
    )

    return sorted_results


# ============================================================
# 18. Match All Teachers
# ============================================================

def run_matching(
    teachers: List[
        Dict[str, Any]
    ],
    hard_requirements: Dict[
        str,
        Any
    ],
    preferred_requirements: Optional[
        Dict[str, Any]
    ] = None,
    top_n: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    对全部老师执行匹配。
    """

    if preferred_requirements is None:
        preferred_requirements = {}

    if not teachers:
        return []

    results = []

    for teacher in teachers:

        result = (
            match_teacher(
                teacher=teacher,
                hard_requirements=(
                    hard_requirements
                ),
                preferred_requirements=(
                    preferred_requirements
                ),
            )
        )

        results.append(
            result
        )

    results = (
        sort_matching_results(
            results
        )
    )

    if top_n is None:
        top_n = TOP_N

    if (
        top_n
        is not None
        and top_n > 0
    ):
        return (
            results[
                :top_n
            ]
        )

    return results


# ============================================================
# 19. Matching Summary
# ============================================================

def build_matching_summary(
    results: List[
        Dict[str, Any]
    ]
) -> Dict[str, Any]:
    """
    给 Streamlit 页面使用的匹配统计。
    """

    total_results = (
        len(
            results
        )
    )

    eligible_count = 0

    high_match_count = 0

    for result in results:

        if result.get(
            "eligible"
        ):
            eligible_count += 1

        if (
            result.get(
                "score",
                0
            )
            >= 80
        ):
            high_match_count += 1

    best_score = 0

    if results:
        best_score = (
            results[0].get(
                "score",
                0
            )
        )

    return {
        "total_results": (
            total_results
        ),

        "eligible_count": (
            eligible_count
        ),

        "high_match_count": (
            high_match_count
        ),

        "best_score": (
            best_score
        ),
    }
