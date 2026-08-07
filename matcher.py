# ============================================================
# Teacher Matching System V1.1
# matcher.py
# ============================================================

from typing import Any, Dict, List, Optional

from config import (
    BOOLEAN_FIELDS,
    DEGREE_RANK,
    HARD_REQUIREMENT_WEIGHT,
    MULTI_SELECT_FIELDS,
    PREFERRED_REQUIREMENT_WEIGHT,
    REFERENCE_REQUIREMENT_WEIGHT,
    TOP_N,
)


# ============================================================
# 1. Helpers
# ============================================================

def ensure_list(
    value: Any
):

    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def normalize_text(
    value: Any
):

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

    if value is None:
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


# ============================================================
# 2. Basic Match
# ============================================================

def match_exact_text(
    actual,
    expected,
):

    return (
        normalize_text(actual)
        ==
        normalize_text(expected)
    )


def match_boolean(
    actual,
    expected,
):

    return (
        bool(actual)
        ==
        bool(expected)
    )


def match_multi(
    actual,
    expected,
    mode="all",
):

    actual_values = {
        normalize_text(item)
        for item in ensure_list(actual)
    }

    expected_values = {
        normalize_text(item)
        for item in ensure_list(expected)
    }

    if not expected_values:
        return True

    if mode == "any":

        return bool(
            actual_values
            &
            expected_values
        )

    return expected_values.issubset(
        actual_values
    )


# ============================================================
# 3. Working City
# ============================================================

def match_working_city(
    teacher,
    required_city,
):

    cities = teacher.get(
        "Preferred Cities"
    ) or []

    normalized = {
        normalize_text(city)
        for city in cities
    }

    if (
        normalize_text("Any City")
        in normalized
    ):

        return True

    return (
        normalize_text(
            required_city
        )
        in normalized
    )


# ============================================================
# 4. Teacher Age
# ============================================================

def match_maximum_teacher_age(
    teacher,
    maximum_age,
):

    teacher_age = to_number(
        teacher.get(
            "Age"
        )
    )

    maximum = to_number(
        maximum_age
    )

    if (
        teacher_age is None
        or maximum is None
    ):
        return False

    return (
        teacher_age
        <= maximum
    )


def match_minimum_teacher_age(
    teacher,
    minimum_age,
):

    teacher_age = to_number(
        teacher.get(
            "Age"
        )
    )

    minimum = to_number(
        minimum_age
    )

    if (
        teacher_age is None
        or minimum is None
    ):
        return False

    return (
        teacher_age
        >= minimum
    )


# ============================================================
# 5. Teaching Years
# ============================================================

def match_minimum_years(
    teacher,
    required,
):

    actual = to_number(
        teacher.get(
            "Years of Teaching"
        )
    )

    required = to_number(
        required
    )

    if (
        actual is None
        or required is None
    ):
        return False

    return (
        actual >= required
    )


# ============================================================
# 6. Degree
# ============================================================

def match_minimum_degree(
    teacher,
    required_degree,
):

    actual_degree = teacher.get(
        "Highest Degree"
    )

    actual_rank = DEGREE_RANK.get(
        actual_degree
    )

    required_rank = DEGREE_RANK.get(
        required_degree
    )

    if (
        actual_rank is None
        or required_rank is None
    ):

        return False

    return (
        actual_rank
        >= required_rank
    )


# ============================================================
# 7. Private Room
# ============================================================

def match_private_room(
    teacher,
    room_provided,
):

    room_provided = bool(
        room_provided
    )

    teacher_requires = bool(
        teacher.get(
            "Private Room Required"
        )
    )

    # 客户提供独立房间：
    # 无论老师是否强制要求，都可以。
    if room_provided:
        return True

    # 客户不能提供：
    # 只有不要求独立房间的老师可以。
    return not teacher_requires


# ============================================================
# 8. Child Age Reference
# ============================================================

def match_child_age_reference(
    teacher,
    child_age,
) -> Optional[bool]:

    age = to_number(
        child_age
    )

    minimum = to_number(
        teacher.get(
            "Minimum Child Age"
        )
    )

    maximum = to_number(
        teacher.get(
            "Maximum Child Age"
        )
    )

    # 资料没填：
    # 不扣分，标记 Unknown。
    if (
        minimum is None
        or maximum is None
        or age is None
    ):

        return None

    return (
        minimum
        <= age
        <= maximum
    )


# ============================================================
# 9. Generic Match
# ============================================================

def match_field(
    teacher,
    field,
    expected,
    multi_mode="all",
):

    if field == "Working City":

        return match_working_city(
            teacher,
            expected,
        )

    if field == "Maximum Teacher Age":

        return match_maximum_teacher_age(
            teacher,
            expected,
        )

    if field == "Minimum Teacher Age":

        return match_minimum_teacher_age(
            teacher,
            expected,
        )

    if field == "Minimum Years of Teaching":

        return match_minimum_years(
            teacher,
            expected,
        )

    if field == "Minimum Degree":

        return match_minimum_degree(
            teacher,
            expected,
        )

    if field == "Private Room Provided":

        return match_private_room(
            teacher,
            expected,
        )

    if field == "Child Age":

        return match_child_age_reference(
            teacher,
            expected,
        )

    if field in MULTI_SELECT_FIELDS:

        return match_multi(
            teacher.get(field),
            expected,
            mode=multi_mode,
        )

    if field in BOOLEAN_FIELDS:

        return match_boolean(
            teacher.get(field),
            expected,
        )

    return match_exact_text(
        teacher.get(field),
        expected,
    )


# ============================================================
# 10. Evaluate Group
# ============================================================

def evaluate_requirements(
    teacher,
    requirements,
    multi_mode="all",
):

    matched = []

    missing = []

    unknown = []

    for field, expected in (
        requirements.items()
    ):

        result = match_field(
            teacher,
            field,
            expected,
            multi_mode=multi_mode,
        )

        if result is None:

            unknown.append(field)

        elif result:

            matched.append(field)

        else:

            missing.append(field)

    return {
        "matched": matched,
        "missing": missing,
        "unknown": unknown,
    }


# ============================================================
# 11. Score
# ============================================================

def group_ratio(
    result,
):

    matched = len(
        result["matched"]
    )

    missing = len(
        result["missing"]
    )

    total = (
        matched
        +
        missing
    )

    # Unknown 不加入分母
    if total == 0:
        return None

    return (
        matched
        /
        total
    )


def calculate_match_score(
    hard_result,
    preferred_result,
    reference_result,
):

    groups = []

    hard_ratio = group_ratio(
        hard_result
    )

    preferred_ratio = group_ratio(
        preferred_result
    )

    reference_ratio = group_ratio(
        reference_result
    )

    if hard_ratio is not None:

        groups.append(
            (
                hard_ratio,
                HARD_REQUIREMENT_WEIGHT,
            )
        )

    if preferred_ratio is not None:

        groups.append(
            (
                preferred_ratio,
                PREFERRED_REQUIREMENT_WEIGHT,
            )
        )

    if reference_ratio is not None:

        groups.append(
            (
                reference_ratio,
                REFERENCE_REQUIREMENT_WEIGHT,
            )
        )

    if not groups:
        return 0

    weighted_score = sum(
        ratio * weight
        for ratio, weight in groups
    )

    active_weight = sum(
        weight
        for _, weight in groups
    )

    score = (
        weighted_score
        /
        active_weight
        *
        100
    )

    score = round(score)

    # 有硬条件不满足时，
    # 不允许显示成 80%+ 高匹配。
    if hard_result["missing"]:

        score = min(
            score,
            79,
        )

    return score


# ============================================================
# 12. Labels
# ============================================================

FIELD_LABELS = {

    "Nationality": "国籍",

    "Current Country": "当前国家",

    "Working City": "工作城市",

    "Minimum Teacher Age": (
        "老师最低年龄"
    ),

    "Maximum Teacher Age": (
        "老师最高年龄"
    ),

    "Minimum Degree": (
        "最低学历"
    ),

    "Minimum Years of Teaching": (
        "最低教学年限"
    ),

    "Teaching Languages": (
        "教学语言"
    ),

    "Subjects": "学科",

    "Curriculum": "课程体系",

    "Visa / Work Authorization Countries": (
        "签证/工作许可"
    ),

    "Live-in": "住家",

    "Night Care": (
        "带睡/夜间照护"
    ),

    "Private Room Provided": (
        "提供独立房间"
    ),

    "Driving": "驾驶",

    "Willing to Travel": (
        "愿意旅行"
    ),

    "SEN Experience": (
        "SEN经验"
    ),

    "International School Experience": (
        "国际学校经验"
    ),

    "Private Tutoring Experience": (
        "私人辅导经验"
    ),

    "Nanny Educator Experience": (
        "育儿教育经验"
    ),

    "Child Age": (
        "孩子年龄（参考）"
    ),
}


def get_field_label(
    field,
):

    return FIELD_LABELS.get(
        field,
        field,
    )


# ============================================================
# 13. Name
# ============================================================

def get_teacher_name(
    teacher,
):

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
        f"{first_name} {last_name}"
        .strip()
    )

    if full_name:
        return full_name

    return (
        f"Teacher "
        f'{teacher.get("Baserow ID", "")}'
    )


# ============================================================
# 14. Recommendation Reasons
# ============================================================

def build_reasons(
    teacher,
    hard_result,
    preferred_result,
    reference_result,
):

    reasons = []

    for field in hard_result[
        "matched"
    ]:

        reasons.append(
            f"满足硬条件："
            f"{get_field_label(field)}"
        )

    for field in preferred_result[
        "matched"
    ]:

        reasons.append(
            f"满足偏好："
            f"{get_field_label(field)}"
        )

    if (
        "Child Age"
        in reference_result[
            "matched"
        ]
    ):

        reasons.append(
            "孩子年龄处于老师偏好的年龄范围"
        )

    if teacher.get(
        "International School Experience"
    ):

        reasons.append(
            "具有国际学校经验"
        )

    if teacher.get(
        "Private Tutoring Experience"
    ):

        reasons.append(
            "具有私人辅导经验"
        )

    return reasons[:8]


# ============================================================
# 15. Match Teacher
# ============================================================

def match_teacher(
    teacher,
    hard_requirements,
    preferred_requirements=None,
    reference_requirements=None,
):

    if preferred_requirements is None:
        preferred_requirements = {}

    if reference_requirements is None:
        reference_requirements = {}

    hard_result = (
        evaluate_requirements(
            teacher,
            hard_requirements,
            multi_mode="all",
        )
    )

    preferred_result = (
        evaluate_requirements(
            teacher,
            preferred_requirements,
            multi_mode="any",
        )
    )

    reference_result = (
        evaluate_requirements(
            teacher,
            reference_requirements,
            multi_mode="all",
        )
    )

    score = (
        calculate_match_score(
            hard_result,
            preferred_result,
            reference_result,
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

        "eligible": eligible,

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

        "hard_unknown": (
            hard_result[
                "unknown"
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

        "preferred_unknown": (
            preferred_result[
                "unknown"
            ]
        ),

        "reference_matched": (
            reference_result[
                "matched"
            ]
        ),

        "reference_missing": (
            reference_result[
                "missing"
            ]
        ),

        "reference_unknown": (
            reference_result[
                "unknown"
            ]
        ),

        "recommendation_reasons": (
            build_reasons(
                teacher,
                hard_result,
                preferred_result,
                reference_result,
            )
        ),
    }


# ============================================================
# 16. Run Matching
# ============================================================

def run_matching(
    teachers,
    hard_requirements,
    preferred_requirements=None,
    reference_requirements=None,
    top_n=None,
):

    if preferred_requirements is None:
        preferred_requirements = {}

    if reference_requirements is None:
        reference_requirements = {}

    results = []

    for teacher in teachers:

        results.append(
            match_teacher(
                teacher,
                hard_requirements,
                preferred_requirements,
                reference_requirements,
            )
        )

    results.sort(
        key=lambda item: (
            item.get(
                "eligible",
                False,
            ),
            item.get(
                "score",
                0,
            ),
            to_number(
                item.get(
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

    if top_n is None:
        top_n = TOP_N

    return results[:top_n]


# ============================================================
# 17. Summary
# ============================================================

def build_matching_summary(
    results,
):

    eligible_count = sum(
        1
        for result in results
        if result.get(
            "eligible"
        )
    )

    high_match = sum(
        1
        for result in results
        if result.get(
            "score",
            0,
        )
        >= 80
    )

    best_score = (
        results[0].get(
            "score",
            0,
        )
        if results
        else 0
    )

    return {
        "total_results": len(results),
        "eligible_count": eligible_count,
        "high_match_count": high_match,
        "best_score": best_score,
    }
