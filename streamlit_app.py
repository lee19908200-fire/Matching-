# ============================================================
# Teacher Matching System V1
# streamlit_app.py
#
# 负责：
# 1. Streamlit 网页
# 2. 输入雇主需求
# 3. 调用 Gemini 解析
# 4. 读取 Baserow Teachers
# 5. 执行 Matching Engine
# 6. 显示 Top Candidates
# ============================================================

from typing import Any, Dict, List

import streamlit as st

from baserow_client import (
    check_baserow_connection,
    get_teacher_database_summary,
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
# 1. Page Configuration
# ============================================================

st.set_page_config(
    page_title="Teacher Matching System",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 2. Custom CSS
# ============================================================

st.markdown(
    """
    <style>

    .block-container {
        max-width: 1400px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    .main-title {
        font-size: 38px;
        font-weight: 700;
        margin-bottom: 4px;
    }

    .main-subtitle {
        color: #666666;
        font-size: 16px;
        margin-bottom: 28px;
    }

    .section-title {
        font-size: 22px;
        font-weight: 650;
        margin-top: 12px;
        margin-bottom: 12px;
    }

    .teacher-score {
        font-size: 30px;
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
# 3. Helper Functions
# ============================================================

def format_number(
    value: Any
) -> str:
    """
    适合界面显示的数字。
    """

    if value is None:
        return "未填写"

    try:
        number = float(value)

        if number.is_integer():
            return str(
                int(number)
            )

        return str(number)

    except (
        TypeError,
        ValueError,
    ):
        return str(value)


def format_list(
    values: Any
) -> str:
    """
    list 转换为可读文本。
    """

    if not values:
        return "未填写"

    if isinstance(
        values,
        list,
    ):
        return ", ".join(
            str(item)
            for item in values
        )

    return str(values)


def format_location(
    teacher: Dict[str, Any]
) -> str:
    """
    当前所在地，仅展示。
    """

    city = (
        teacher.get(
            "Current City"
        )
        or ""
    )

    country = (
        teacher.get(
            "Current Country"
        )
        or ""
    )

    parts = [
        value
        for value in [
            city,
            country,
        ]
        if value
    ]

    if not parts:
        return "未填写"

    return ", ".join(parts)


def format_age_range(
    teacher: Dict[str, Any]
) -> str:
    """
    老师可接受孩子年龄。
    """

    minimum_age = (
        teacher.get(
            "Minimum Child Age"
        )
    )

    maximum_age = (
        teacher.get(
            "Maximum Child Age"
        )
    )

    if (
        minimum_age is None
        or maximum_age is None
    ):
        return "未填写"

    return (
        f"{format_number(minimum_age)}"
        f"–"
        f"{format_number(maximum_age)} 岁"
    )


def requirement_value_text(
    value: Any
) -> str:
    """
    招聘需求在网页中的显示。
    """

    if isinstance(
        value,
        bool,
    ):
        return (
            "是"
            if value
            else "否"
        )

    if isinstance(
        value,
        list,
    ):
        return ", ".join(
            str(item)
            for item in value
        )

    return str(value)


def render_requirement_group(
    title: str,
    requirements: Dict[str, Any],
):
    """
    在页面显示 hard/preferred requirements。
    """

    st.markdown(
        f"#### {title}"
    )

    if not requirements:
        st.caption(
            "没有识别到条件。"
        )

        return

    for (
        field,
        value,
    ) in requirements.items():

        label = (
            get_field_label(
                field
            )
        )

        st.write(
            f"**{label}：** "
            f"{requirement_value_text(value)}"
        )


def render_teacher_card(
    rank: int,
    result: Dict[str, Any],
):
    """
    显示单个候选老师。
    """

    teacher = (
        result.get(
            "teacher",
            {}
        )
    )

    name = (
        result.get(
            "name"
        )
        or "Unknown Teacher"
    )

    score = (
        result.get(
            "score",
            0
        )
    )

    eligible = (
        result.get(
            "eligible",
            False
        )
    )

    hard_matched = (
        result.get(
            "hard_matched",
            []
        )
    )

    hard_missing = (
        result.get(
            "hard_missing",
            []
        )
    )

    preferred_matched = (
        result.get(
            "preferred_matched",
            []
        )
    )

    preferred_missing = (
        result.get(
            "preferred_missing",
            []
        )
    )

    reasons = (
        result.get(
            "recommendation_reasons",
            []
        )
    )

    with st.container(
        border=True
    ):

        # ----------------------------------------------------
        # Header
        # ----------------------------------------------------

        left,
        right = st.columns(
            [
                4,
                1,
            ]
        )

        with left:

            st.markdown(
                f"### {rank}. {name}"
            )

            if eligible:
                st.success(
                    "符合全部硬条件"
                )

            else:
                st.warning(
                    "未完全符合全部硬条件"
                )

        with right:

            st.metric(
                label="匹配度",
                value=f"{score}%",
            )

        # ----------------------------------------------------
        # Main profile
        # ----------------------------------------------------

        col1,
        col2,
        col3 = st.columns(3)

        with col1:

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

        with col2:

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

        with col3:

            st.write(
                "**Curriculum：**",
                format_list(
                    teacher.get(
                        "Curriculum"
                    )
                ),
            )

            st.write(
                "**Subjects：**",
                format_list(
                    teacher.get(
                        "Subjects"
                    )
                ),
            )

            st.write(
                "**Live-in：**",
                (
                    "是"
                    if teacher.get(
                        "Live-in"
                    )
                    else "否"
                ),
            )

            st.write(
                "**Driving：**",
                (
                    "是"
                    if teacher.get(
                        "Driving"
                    )
                    else "否"
                ),
            )

        # ----------------------------------------------------
        # Matching Analysis
        # ----------------------------------------------------

        st.markdown(
            "#### 匹配分析"
        )

        matched_labels = [
            get_field_label(
                field
            )
            for field in hard_matched
        ]

        missing_labels = [
            get_field_label(
                field
            )
            for field in hard_missing
        ]

        preferred_labels = [
            get_field_label(
                field
            )
            for field in preferred_matched
        ]

        preferred_missing_labels = [
            get_field_label(
                field
            )
            for field in preferred_missing
        ]

        st.write(
            "✅ **硬条件满足：**",
            (
                ", ".join(
                    matched_labels
                )
                if matched_labels
                else "无"
            ),
        )

        st.write(
            "❌ **硬条件缺失：**",
            (
                ", ".join(
                    missing_labels
                )
                if missing_labels
                else "无"
            ),
        )

        st.write(
            "⭐ **偏好条件满足：**",
            (
                ", ".join(
                    preferred_labels
                )
                if preferred_labels
                else "无"
            ),
        )

        if preferred_missing_labels:

            st.write(
                "△ **偏好条件未满足：**",
                ", ".join(
                    preferred_missing_labels
                ),
            )

        # ----------------------------------------------------
        # Recommendation Reasons
        # ----------------------------------------------------

        if reasons:

            st.markdown(
                "#### 推荐理由"
            )

            for reason in reasons:

                st.write(
                    f"• {reason}"
                )

        # ----------------------------------------------------
        # Optional additional info
        # ----------------------------------------------------

        with st.expander(
            "查看完整老师资料"
        ):

            display_teacher = {
                key: value
                for (
                    key,
                    value,
                ) in teacher.items()
                if not key.startswith(
                    "_"
                )
            }

            st.json(
                display_teacher
            )

        validation_warnings = (
            teacher.get(
                "_validation_warnings",
                []
            )
        )

        if validation_warnings:

            with st.expander(
                "数据库资料提示"
            ):

                for warning in (
                    validation_warnings
                ):

                    st.warning(
                        warning
                    )


# ============================================================
# 4. System Configuration Check
# ============================================================

config_errors = (
    validate_config()
)

if config_errors:

    st.error(
        "系统尚未配置完成。"
    )

    for error in (
        config_errors
    ):

        st.write(
            f"- {error}"
        )

    st.info(
        "部署 Streamlit 时，请在 "
        "App Settings → Secrets 中配置 "
        "BASEROW_TOKEN、TABLE_ID、"
        "GEMINI_API_KEY 和 GEMINI_MODEL。"
    )

    st.stop()


# ============================================================
# 5. Sidebar
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
    # Baserow Health
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
    # Gemini Health
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
    # Database summary
    # --------------------------------------------------------

    st.markdown(
        "### 老师数据库"
    )

    try:

        database_summary = (
            get_teacher_database_summary()
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

    except Exception as error:

        st.warning(
            "无法读取数据库统计"
        )

        st.caption(
            str(error)
        )

    st.divider()

    st.caption(
        "Current City 与 Desired Position "
        "仅用于展示，不参与匹配评分。"
    )


# ============================================================
# 6. Main Header
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
# 7. Load Teachers
# ============================================================

try:

    teachers = (
        load_teachers()
    )

except Exception as error:

    st.error(
        "无法读取 Teachers 数据库。"
    )

    st.exception(
        error
    )

    st.stop()


if not teachers:

    st.warning(
        "Teachers 数据库中没有有效老师资料。"
    )

    st.stop()


# ============================================================
# 8. Employer Requirement Input
# ============================================================

st.markdown(
    '<div class="section-title">'
    '1. 输入雇主需求'
    '</div>',
    unsafe_allow_html=True,
)


example_request = (
    "杭州家庭寻找一位住家育儿老师，照顾2岁孩子。\n"
    "老师必须愿意在杭州工作，并且有早教经验。\n"
    "最好有5年以上教学或育儿经验。"
)


employer_request = st.text_area(
    label="雇主需求",
    value="",
    height=190,
    placeholder=example_request,
)


button_col1, button_col2 = st.columns([4, 1])


with button_col1:

    start_matching = (
        st.button(
            "开始匹配",
            type="primary",
            use_container_width=True,
        )
    )


with button_col2:

    if st.button(
        "清除结果",
        use_container_width=True,
    ):

        for key in [
            "parsed_requirements",
            "matching_results",
            "employer_request_saved",
        ]:

            if key in (
                st.session_state
            ):

                del (
                    st.session_state[
                        key
                    ]
                )

        st.rerun()


# ============================================================
# 9. Run Matching
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

                matching_results = (
                    run_matching(
                        teachers=teachers,
                        hard_requirements=(
                            parsed_requirements[
                                "hard_requirements"
                            ]
                        ),
                        preferred_requirements=(
                            parsed_requirements[
                                "preferred_requirements"
                            ]
                        ),
                        top_n=TOP_N,
                    )
                )

                st.session_state[
                    "parsed_requirements"
                ] = (
                    parsed_requirements
                )

                st.session_state[
                    "matching_results"
                ] = (
                    matching_results
                )

                st.session_state[
                    "employer_request_saved"
                ] = (
                    cleaned_request
                )

            except Exception as error:

                st.error(
                    "匹配过程中发生错误。"
                )

                st.exception(
                    error
                )


# ============================================================
# 10. Retrieve Saved Results
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
# 11. Parsed Requirements UI
# ============================================================

if parsed_requirements:

    st.divider()

    st.markdown(
        '<div class="section-title">'
        '2. AI 解析后的招聘条件'
        '</div>',
        unsafe_allow_html=True,
    )

    if saved_request:

        with st.expander(
            "查看原始雇主需求"
        ):

            st.write(
                saved_request
            )

    hard_col,
    preferred_col = (
        st.columns(2)
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
# 12. Matching Results UI
# ============================================================

if matching_results is not None:

    st.divider()

    st.markdown(
        '<div class="section-title">'
        '3. 推荐老师'
        '</div>',
        unsafe_allow_html=True,
    )

    summary = (
        build_matching_summary(
            matching_results
        )
    )

    metric1,
    metric2,
    metric3,
    metric4 = st.columns(4)

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

        st.metric(
            "最高匹配度",
            (
                f'{summary.get("best_score", 0)}%'
            ),
        )

    if not matching_results:

        st.warning(
            "目前没有匹配结果。"
        )

    else:

        for (
            index,
            result,
        ) in enumerate(
            matching_results,
            start=1,
        ):

            render_teacher_card(
                rank=index,
                result=result,
            )


# ============================================================
# 13. Footer
# ============================================================

st.divider()

st.caption(
    "Teacher Matching System V1 · "
    "Baserow + Gemini + Streamlit"
)
