# ============================================================
# Teacher Matching System V1
# streamlit_app.py
#
# 功能：
# 1. Streamlit 网页
# 2. 输入雇主自然语言需求
# 3. Gemini 自动解析需求
# 4. Baserow 自动读取老师数据库
# 5. Matching Engine 自动评分
# 6. 显示 Top Candidates
# ============================================================


# ============================================================
# 1. Imports
# ============================================================

from typing import Any, Dict, List

import streamlit as st

from baserow_client import (
    check_baserow_connection,
    load_teachers,
)

from config import (
    TOP_N,
    validate_config,
)

from gemini_parser import (
    check_gemini_connection,
    parse_employer_requirement,
)

from matcher import (
    build_matching_summary,
    get_field_label,
    run_matching,
)


# ============================================================
# 2. Streamlit Page Configuration
# ============================================================

st.set_page_config(
    page_title="Teacher Matching System",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 3. Custom CSS
# ============================================================

st.markdown(
    """
    <style>

    .block-container {
        max-width: 1450px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    .main-title {
        font-size: 42px;
        font-weight: 750;
        margin-bottom: 5px;
    }

    .main-subtitle {
        color: #777777;
        font-size: 16px;
        margin-bottom: 32px;
    }

    .section-title {
        font-size: 25px;
        font-weight: 700;
        margin-top: 14px;
        margin-bottom: 15px;
    }

    .teacher-name {
        font-size: 23px;
        font-weight: 700;
    }

    .small-muted {
        font-size: 13px;
        color: #777777;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 4. Formatting Helpers
# ============================================================

def format_number(value: Any) -> str:
    """
    数字显示格式。
    """

    if value is None:
        return "未填写"

    try:
        number = float(value)

        if number.is_integer():
            return str(int(number))

        return str(round(number, 2))

    except (TypeError, ValueError):
        return str(value)


def format_list(values: Any) -> str:
    """
    List 转换成文字。
    """

    if values is None:
        return "未填写"

    if values == "":
        return "未填写"

    if isinstance(values, list):

        if not values:
            return "未填写"

        return ", ".join(
            str(item)
            for item in values
        )

    return str(values)


def yes_no(value: Any) -> str:
    """
    Boolean 中文显示。
    """

    return "是" if bool(value) else "否"


def format_location(
    teacher: Dict[str, Any]
) -> str:
    """
    当前所在地，仅展示，不参与 Working City 匹配。
    """

    city = teacher.get(
        "Current City"
    ) or ""

    country = teacher.get(
        "Current Country"
    ) or ""

    parts = []

    if city:
        parts.append(str(city))

    if country:
        parts.append(str(country))

    if not parts:
        return "未填写"

    return ", ".join(parts)


def format_age_range(
    teacher: Dict[str, Any]
) -> str:
    """
    老师可接受孩子年龄。
    """

    minimum_age = teacher.get(
        "Minimum Child Age"
    )

    maximum_age = teacher.get(
        "Maximum Child Age"
    )

    if (
        minimum_age is None
        and maximum_age is None
    ):
        return "未填写"

    if minimum_age is None:
        return (
            f"≤ {format_number(maximum_age)} 岁"
        )

    if maximum_age is None:
        return (
            f"≥ {format_number(minimum_age)} 岁"
        )

    return (
        f"{format_number(minimum_age)}"
        f"–"
        f"{format_number(maximum_age)} 岁"
    )


def requirement_value_text(
    value: Any
) -> str:
    """
    AI Requirement 页面显示。
    """

    if isinstance(value, bool):
        return "是" if value else "否"

    if isinstance(value, list):

        return ", ".join(
            str(item)
            for item in value
        )

    return str(value)


# ============================================================
# 5. Database Summary
# ============================================================

def build_database_summary(
    teachers: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    根据已经读取的老师列表计算数据库统计，
    避免再次请求 Baserow。
    """

    total_teachers = len(teachers)

    complete_age_range = 0
    with_preferred_cities = 0
    with_visa_countries = 0
    teachers_with_warnings = 0

    for teacher in teachers:

        minimum_age = teacher.get(
            "Minimum Child Age"
        )

        maximum_age = teacher.get(
            "Maximum Child Age"
        )

        if (
            minimum_age is not None
            and maximum_age is not None
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
        "total_teachers": total_teachers,
        "complete_age_range": complete_age_range,
        "with_preferred_cities": with_preferred_cities,
        "with_visa_countries": with_visa_countries,
        "teachers_with_warnings": teachers_with_warnings,
    }


# ============================================================
# 6. Requirement Display
# ============================================================

def render_requirement_group(
    title: str,
    requirements: Dict[str, Any],
):
    """
    显示 Hard / Preferred Requirements。
    """

    st.markdown(
        f"#### {title}"
    )

    if not requirements:

        st.caption(
            "没有识别到条件。"
        )

        return

    for field, value in requirements.items():

        label = get_field_label(
            field
        )

        value_text = (
            requirement_value_text(
                value
            )
        )

        st.write(
            f"**{label}：** {value_text}"
        )


# ============================================================
# 7. Teacher Card
# ============================================================

def render_teacher_card(
    rank: int,
    result: Dict[str, Any],
):
    """
    显示单个老师匹配结果。
    """

    teacher = result.get(
        "teacher",
        {}
    )

    name = (
        result.get("name")
        or "Unknown Teacher"
    )

    score = result.get(
        "score",
        0
    )

    eligible = result.get(
        "eligible",
        False
    )

    hard_matched = result.get(
        "hard_matched",
        []
    )

    hard_missing = result.get(
        "hard_missing",
        []
    )

    preferred_matched = result.get(
        "preferred_matched",
        []
    )

    preferred_missing = result.get(
        "preferred_missing",
        []
    )

    reasons = result.get(
        "recommendation_reasons",
        []
    )

    with st.container(
        border=True
    ):

        # ====================================================
        # Header
        # ====================================================

        header_left, header_right = st.columns(
            [4, 1]
        )

        with header_left:

            st.markdown(
                f"### {rank}. {name}"
            )

            if eligible:

                st.success(
                    "✅ 符合全部硬条件"
                )

            else:

                st.warning(
                    "⚠️ 未完全符合全部硬条件"
                )

        with header_right:

            st.metric(
                "匹配度",
                f"{score}%",
            )

        # ====================================================
        # Basic Profile
        # ====================================================

        profile_col1, profile_col2, profile_col3 = st.columns(
            3
        )

        with profile_col1:

            st.write(
                "**国籍：**",
                teacher.get(
                    "Nationality"
                )
                or "未填写",
            )

            st.write(
                "**当前所在地：**",
                format_location(
                    teacher
                ),
            )

            st.write(
                "**教学年限：**",
                format_number(
                    teacher.get(
                        "Years of Teaching"
                    )
                ),
            )

            st.write(
                "**最高学历：**",
                teacher.get(
                    "Highest Degree"
                )
                or "未填写",
            )

        with profile_col2:

            st.write(
                "**可接受工作城市：**",
                format_list(
                    teacher.get(
                        "Preferred Cities"
                    )
                ),
            )

            st.write(
                "**可接受孩子年龄：**",
                format_age_range(
                    teacher
                ),
            )

            st.write(
                "**签证/合法工作国家：**",
                format_list(
                    teacher.get(
                        "Visa / Work Authorization Countries"
                    )
                ),
            )

            st.write(
                "**教学语言：**",
                format_list(
                    teacher.get(
                        "Teaching Languages"
                    )
                ),
            )

        with profile_col3:

            st.write(
                "**Subjects：**",
                format_list(
                    teacher.get(
                        "Subjects"
                    )
                ),
            )

            st.write(
                "**Curriculum：**",
                format_list(
                    teacher.get(
                        "Curriculum"
                    )
                ),
            )

            st.write(
                "**Live-in：**",
                yes_no(
                    teacher.get(
                        "Live-in"
                    )
                ),
            )

            st.write(
                "**Driving：**",
                yes_no(
                    teacher.get(
                        "Driving"
                    )
                ),
            )

        # ====================================================
        # More Experience
        # ====================================================

        experience_col1, experience_col2, experience_col3 = st.columns(
            3
        )

        with experience_col1:

            st.write(
                "**SEN Experience：**",
                yes_no(
                    teacher.get(
                        "SEN Experience"
                    )
                ),
            )

        with experience_col2:

            st.write(
                "**International School：**",
                yes_no(
                    teacher.get(
                        "International School Experience"
                    )
                ),
            )

        with experience_col3:

            st.write(
                "**Private Tutoring：**",
                yes_no(
                    teacher.get(
                        "Private Tutoring Experience"
                    )
                ),
            )

        st.divider()

        # ====================================================
        # Matching Analysis
        # ====================================================

        st.markdown(
            "#### 匹配分析"
        )

        hard_matched_labels = [
            get_field_label(field)
            for field in hard_matched
        ]

        hard_missing_labels = [
            get_field_label(field)
            for field in hard_missing
        ]

        preferred_matched_labels = [
            get_field_label(field)
            for field in preferred_matched
        ]

        preferred_missing_labels = [
            get_field_label(field)
            for field in preferred_missing
        ]

        st.write(
            "✅ **硬条件满足：**",
            (
                ", ".join(
                    hard_matched_labels
                )
                if hard_matched_labels
                else "无"
            ),
        )

        st.write(
            "❌ **硬条件缺失：**",
            (
                ", ".join(
                    hard_missing_labels
                )
                if hard_missing_labels
                else "无"
            ),
        )

        st.write(
            "⭐ **偏好条件满足：**",
            (
                ", ".join(
                    preferred_matched_labels
                )
                if preferred_matched_labels
                else "无"
            ),
        )

        st.write(
            "△ **偏好条件未满足：**",
            (
                ", ".join(
                    preferred_missing_labels
                )
                if preferred_missing_labels
                else "无"
            ),
        )

        # ====================================================
        # Recommendation Reasons
        # ====================================================

        if reasons:

            st.markdown(
                "#### 推荐理由"
            )

            for reason in reasons:

                st.write(
                    f"• {reason}"
                )

        # ====================================================
        # Desired Position
        # ====================================================

        desired_positions = teacher.get(
            "Desired Position"
        )

        if desired_positions:

            st.caption(
                "Desired Position（仅展示，不参与匹配）："
                +
                format_list(
                    desired_positions
                )
            )

        # ====================================================
        # Full Profile
        # ====================================================

        with st.expander(
            "查看完整老师资料"
        ):

            display_teacher = {}

            for key, value in teacher.items():

                if str(key).startswith("_"):
                    continue

                display_teacher[
                    key
                ] = value

            st.json(
                display_teacher
            )

        # ====================================================
        # Database Validation
        # ====================================================

        validation_warnings = teacher.get(
            "_validation_warnings",
            []
        )

        if validation_warnings:

            with st.expander(
                "数据库资料提示"
            ):

                for warning in validation_warnings:

                    st.warning(
                        warning
                    )


# ============================================================
# 8. Configuration Validation
# ============================================================

config_errors = validate_config()

if config_errors:

    st.error(
        "系统配置尚未完成。"
    )

    for error in config_errors:

        st.write(
            f"• {error}"
        )

    st.info(
        "请进入 Streamlit → "
        "Manage app → Settings → Secrets "
        "配置 Baserow 和 Gemini。"
    )

    st.stop()


# ============================================================
# 9. Load Teachers
# ============================================================

try:

    teachers = load_teachers()

except Exception as error:

    st.error(
        "无法读取 Baserow Teachers 数据库。"
    )

    st.exception(
        error
    )

    st.stop()


if not teachers:

    st.warning(
        "Baserow 中没有有效老师资料。"
    )

    st.stop()


database_summary = (
    build_database_summary(
        teachers
    )
)


# ============================================================
# 10. Sidebar
# ============================================================

with st.sidebar:

    st.title(
        "🎓 Teacher Matching"
    )

    st.caption(
        "AI-assisted recruitment matching system"
    )

    st.divider()

    st.markdown(
        "### 系统状态"
    )

    # --------------------------------------------------------
    # Baserow
    # --------------------------------------------------------

    baserow_status = (
        check_baserow_connection()
    )

    if baserow_status.get(
        "success"
    ):

        st.success(
            "Baserow 已连接"
        )

    else:

        st.error(
            "Baserow 连接失败"
        )

        st.caption(
            baserow_status.get(
                "message",
                "",
            )
        )

    # --------------------------------------------------------
    # Gemini
    # --------------------------------------------------------

    gemini_status = (
        check_gemini_connection()
    )

    if gemini_status.get(
        "success"
    ):

        st.success(
            "Gemini 已连接"
        )

        active_model = (
            gemini_status.get(
                "model"
            )
        )

        if active_model:

            st.caption(
                f"模型：{active_model}"
            )

    else:

        st.error(
            "Gemini 连接失败"
        )

        st.caption(
            gemini_status.get(
                "message",
                "",
            )
        )

    st.divider()

    # --------------------------------------------------------
    # Database Summary
    # --------------------------------------------------------

    st.markdown(
        "### 老师数据库"
    )

    st.metric(
        "老师总数",
        database_summary.get(
            "total_teachers",
            0,
        ),
    )

    st.caption(
        "已填写孩子年龄范围："
        f'{database_summary.get("complete_age_range", 0)}'
    )

    st.caption(
        "已填写可接受城市："
        f'{database_summary.get("with_preferred_cities", 0)}'
    )

    st.caption(
        "已填写签证国家："
        f'{database_summary.get("with_visa_countries", 0)}'
    )

    warning_count = (
        database_summary.get(
            "teachers_with_warnings",
            0,
        )
    )

    if warning_count:

        st.warning(
            f"{warning_count} 位老师资料存在缺失"
        )

    st.divider()

    st.caption(
        "Current City 仅展示，"
        "不作为 Working City 匹配条件。"
    )

    st.caption(
        "Desired Position 仅展示，"
        "不参与候选人筛选。"
    )


# ============================================================
# 11. Main Header
# ============================================================

st.markdown(
    """
    <div class="main-title">
        AI Teacher Matching System
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="main-subtitle">
        输入雇主需求，Gemini 自动解析招聘条件，
        系统从 Baserow 教师数据库中筛选并排序候选人。
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 12. Employer Requirement Input
# ============================================================

st.markdown(
    """
    <div class="section-title">
        1. 输入雇主需求
    </div>
    """,
    unsafe_allow_html=True,
)


example_request = (
    "北京家庭寻找一位住家育儿老师，"
    "照顾4岁孩子。\n"
    "老师必须愿意在北京工作，"
    "英语流利，本科以上。\n"
    "最好有5年以上教学或育儿经验。"
)


employer_request = st.text_area(
    label="雇主需求",
    value="",
    height=190,
    placeholder=example_request,
)


# ============================================================
# 13. Buttons
# ============================================================

button_col1, button_col2 = st.columns(
    [4, 1]
)

with button_col1:

    start_matching = st.button(
        "开始匹配",
        type="primary",
        use_container_width=True,
    )

with button_col2:

    clear_results = st.button(
        "清除结果",
        use_container_width=True,
    )


if clear_results:

    session_keys = [
        "parsed_requirements",
        "matching_results",
        "employer_request_saved",
    ]

    for key in session_keys:

        if key in st.session_state:

            del st.session_state[
                key
            ]

    st.rerun()


# ============================================================
# 14. Run Matching
# ============================================================

if start_matching:

    cleaned_request = (
        employer_request
        .strip()
    )

    if not cleaned_request:

        st.warning(
            "请先输入雇主需求。"
        )

    else:

        with st.spinner(
            "Gemini 正在解析招聘需求并匹配老师..."
        ):

            try:

                parsed_requirements = (
                    parse_employer_requirement(
                        cleaned_request
                    )
                )

                hard_requirements = (
                    parsed_requirements.get(
                        "hard_requirements",
                        {},
                    )
                )

                preferred_requirements = (
                    parsed_requirements.get(
                        "preferred_requirements",
                        {},
                    )
                )

                matching_results = (
                    run_matching(
                        teachers=teachers,
                        hard_requirements=hard_requirements,
                        preferred_requirements=preferred_requirements,
                        top_n=TOP_N,
                    )
                )

                st.session_state[
                    "parsed_requirements"
                ] = parsed_requirements

                st.session_state[
                    "matching_results"
                ] = matching_results

                st.session_state[
                    "employer_request_saved"
                ] = cleaned_request

            except Exception as error:

                st.error(
                    "匹配过程中发生错误。"
                )

                st.exception(
                    error
                )


# ============================================================
# 15. Session Results
# ============================================================

parsed_requirements = (
    st.session_state.get(
        "parsed_requirements"
    )
)

matching_results = (
    st.session_state.get(
        "matching_results"
    )
)

saved_request = (
    st.session_state.get(
        "employer_request_saved"
    )
)


# ============================================================
# 16. AI Parsed Requirements
# ============================================================

if parsed_requirements:

    st.divider()

    st.markdown(
        """
        <div class="section-title">
            2. AI 解析后的招聘条件
        </div>
        """,
        unsafe_allow_html=True,
    )

    if saved_request:

        with st.expander(
            "查看原始雇主需求"
        ):

            st.write(
                saved_request
            )

    model_used = (
        parsed_requirements.get(
            "model_used"
        )
    )

    if model_used:

        st.caption(
            f"Gemini Model：{model_used}"
        )

    # IMPORTANT:
    # 必须在同一条 Python 语句中赋值
    hard_col, preferred_col = st.columns(
        2
    )

    with hard_col:

        render_requirement_group(
            title="必须条件",
            requirements=(
                parsed_requirements.get(
                    "hard_requirements",
                    {},
                )
            ),
        )

    with preferred_col:

        render_requirement_group(
            title="偏好条件",
            requirements=(
                parsed_requirements.get(
                    "preferred_requirements",
                    {},
                )
            ),
        )

    warnings = (
        parsed_requirements.get(
            "warnings",
            []
        )
    )

    if warnings:

        with st.expander(
            "AI 标准化提示"
        ):

            for warning in warnings:

                st.warning(
                    warning
                )

    with st.expander(
        "查看 Gemini 原始结构化结果"
    ):

        st.json(
            parsed_requirements.get(
                "raw_requirements",
                {},
            )
        )


# ============================================================
# 17. Matching Results
# ============================================================

if matching_results is not None:

    st.divider()

    st.markdown(
        """
        <div class="section-title">
            3. 推荐老师
        </div>
        """,
        unsafe_allow_html=True,
    )

    summary = (
        build_matching_summary(
            matching_results
        )
    )

    metric1, metric2, metric3, metric4 = st.columns(
        4
    )

    with metric1:

        st.metric(
            "显示候选人",
            summary.get(
                "total_results",
                0,
            ),
        )

    with metric2:

        st.metric(
            "符合全部硬条件",
            summary.get(
                "eligible_count",
                0,
            ),
        )

    with metric3:

        st.metric(
            "80%+ 匹配",
            summary.get(
                "high_match_count",
                0,
            ),
        )

    with metric4:

        best_score = (
            summary.get(
                "best_score",
                0,
            )
        )

        st.metric(
            "最高匹配度",
            f"{best_score}%",
        )

    if not matching_results:

        st.warning(
            "目前没有匹配结果。"
        )

    else:

        for index, result in enumerate(
            matching_results,
            start=1,
        ):

            render_teacher_card(
                rank=index,
                result=result,
            )


# ============================================================
# 18. Footer
# ============================================================

st.divider()

st.caption(
    "Teacher Matching System V1 · "
    "Baserow + Gemini + Streamlit"
)
