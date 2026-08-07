# ============================================================
# Teacher Matching System V1.1
# streamlit_app.py
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
# Page
# ============================================================

st.set_page_config(
    page_title="Teacher Matching System",
    page_icon="🎓",
    layout="wide",
)


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
    }

    .main-subtitle {
        color: #777777;
        margin-bottom: 30px;
    }

    .section-title {
        font-size: 25px;
        font-weight: 700;
        margin-top: 15px;
        margin-bottom: 15px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Helpers
# ============================================================

def format_number(
    value: Any
):

    if value is None:
        return "未填写"

    try:

        number = float(value)

        if number.is_integer():
            return str(
                int(number)
            )

        return str(
            round(number, 2)
        )

    except (
        TypeError,
        ValueError,
    ):

        return str(value)


def format_list(
    value: Any
):

    if value is None:
        return "未填写"

    if isinstance(value, list):

        if not value:
            return "未填写"

        return ", ".join(
            str(item)
            for item in value
        )

    return str(value)


def yes_no(
    value: Any
):

    return (
        "是"
        if bool(value)
        else "否"
    )


def format_location(
    teacher,
):

    city = teacher.get(
        "Current City"
    )

    country = teacher.get(
        "Current Country"
    )

    values = []

    if city:
        values.append(
            str(city)
        )

    if country:
        values.append(
            str(country)
        )

    if not values:
        return "未填写"

    return ", ".join(values)


def format_age_range(
    teacher,
):

    minimum = teacher.get(
        "Minimum Child Age"
    )

    maximum = teacher.get(
        "Maximum Child Age"
    )

    if (
        minimum is None
        or maximum is None
    ):

        return "未填写"

    return (
        f"{format_number(minimum)}"
        "–"
        f"{format_number(maximum)} 岁"
    )


def requirement_text(
    value,
):

    if isinstance(value, bool):

        return (
            "是"
            if value
            else "否"
        )

    if isinstance(value, list):

        return ", ".join(
            str(item)
            for item in value
        )

    return str(value)


# ============================================================
# Requirement Group
# ============================================================

def render_requirement_group(
    title,
    requirements,
):

    st.markdown(
        f"#### {title}"
    )

    if not requirements:

        st.caption(
            "没有识别到条件"
        )

        return

    for field, value in (
        requirements.items()
    ):

        st.write(
            f"**{get_field_label(field)}：** "
            f"{requirement_text(value)}"
        )


# ============================================================
# Teacher Card
# ============================================================

def render_teacher_card(
    rank,
    result,
):

    teacher = result[
        "teacher"
    ]

    with st.container(
        border=True
    ):

        header_left, header_right = st.columns(
            [4, 1]
        )

        with header_left:

            st.markdown(
                f"### {rank}. "
                f'{result["name"]}'
            )

            if result[
                "eligible"
            ]:

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
                f'{result["score"]}%'
            )

        col1, col2, col3 = st.columns(
            3
        )

        with col1:

            st.write(
                "**年龄：**",
                (
                    format_number(
                        teacher.get(
                            "Age"
                        )
                    )
                    + " 岁"
                    if teacher.get(
                        "Age"
                    )
                    is not None
                    else "未填写"
                ),
            )

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
                "**教学语言：**",
                format_list(
                    teacher.get(
                        "Teaching Languages"
                    )
                ),
            )

            st.write(
                "**签证/工作许可：**",
                format_list(
                    teacher.get(
                        "Visa / Work Authorization Countries"
                    )
                ),
            )

        with col3:

            st.write(
                "**住家：**",
                yes_no(
                    teacher.get(
                        "Live-in"
                    )
                ),
            )

            st.write(
                "**可以带睡/夜间照护：**",
                yes_no(
                    teacher.get(
                        "Night Care"
                    )
                ),
            )

            st.write(
                "**要求独立房间：**",
                yes_no(
                    teacher.get(
                        "Private Room Required"
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

        st.divider()

        st.markdown(
            "#### 匹配分析"
        )

        hard_matched = [
            get_field_label(field)
            for field in result[
                "hard_matched"
            ]
        ]

        hard_missing = [
            get_field_label(field)
            for field in result[
                "hard_missing"
            ]
        ]

        preferred_matched = [
            get_field_label(field)
            for field in result[
                "preferred_matched"
            ]
        ]

        preferred_missing = [
            get_field_label(field)
            for field in result[
                "preferred_missing"
            ]
        ]

        reference_matched = [
            get_field_label(field)
            for field in result[
                "reference_matched"
            ]
        ]

        reference_missing = [
            get_field_label(field)
            for field in result[
                "reference_missing"
            ]
        ]

        reference_unknown = [
            get_field_label(field)
            for field in result[
                "reference_unknown"
            ]
        ]

        st.write(
            "✅ **硬条件满足：**",
            ", ".join(
                hard_matched
            )
            or "无",
        )

        st.write(
            "❌ **硬条件缺失：**",
            ", ".join(
                hard_missing
            )
            or "无",
        )

        st.write(
            "⭐ **偏好满足：**",
            ", ".join(
                preferred_matched
            )
            or "无",
        )

        st.write(
            "△ **偏好未满足：**",
            ", ".join(
                preferred_missing
            )
            or "无",
        )

        st.write(
            "ℹ️ **参考条件适配：**",
            ", ".join(
                reference_matched
            )
            or "无",
        )

        st.write(
            "ℹ️ **参考条件不适配：**",
            ", ".join(
                reference_missing
            )
            or "无",
        )

        if reference_unknown:

            st.write(
                "ℹ️ **参考资料未知：**",
                ", ".join(
                    reference_unknown
                ),
            )

        reasons = result.get(
            "recommendation_reasons",
            []
        )

        if reasons:

            st.markdown(
                "#### 推荐理由"
            )

            for reason in reasons:

                st.write(
                    f"• {reason}"
                )

        desired = teacher.get(
            "Desired Position"
        )

        if desired:

            st.caption(
                "Desired Position "
                "仅展示，不参与匹配："
                f"{format_list(desired)}"
            )

        with st.expander(
            "查看完整老师资料"
        ):

            clean_teacher = {
                key: value
                for key, value
                in teacher.items()
                if not str(
                    key
                ).startswith("_")
            }

            st.json(
                clean_teacher
            )


# ============================================================
# Configuration
# ============================================================

errors = validate_config()

if errors:

    st.error(
        "系统配置不完整"
    )

    for error in errors:

        st.write(
            error
        )

    st.stop()


# ============================================================
# Teachers
# ============================================================

try:

    teachers = load_teachers()

except Exception as error:

    st.error(
        "无法读取老师数据库"
    )

    st.exception(
        error
    )

    st.stop()


# ============================================================
# Sidebar
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

    baserow_status = (
        check_baserow_connection()
    )

    if baserow_status[
        "success"
    ]:

        st.success(
            "Baserow 已连接"
        )

    else:

        st.error(
            "Baserow 连接失败"
        )

        st.caption(
            baserow_status[
                "message"
            ]
        )

    gemini_status = (
        check_gemini_connection()
    )

    if gemini_status[
        "success"
    ]:

        st.success(
            "Gemini 已连接"
        )

        if gemini_status.get(
            "model"
        ):

            st.caption(
                "模型："
                f'{gemini_status["model"]}'
            )

    else:

        st.error(
            "Gemini 连接失败"
        )

        st.caption(
            gemini_status[
                "message"
            ]
        )

    st.divider()

    st.markdown(
        "### 老师数据库"
    )

    st.metric(
        "老师总数",
        len(teachers),
    )


# ============================================================
# Header
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
    输入雇主需求，Gemini 自动解析，
    Baserow 自动读取老师资料并执行匹配。
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Input
# ============================================================

st.markdown(
    """
    <div class="section-title">
    1. 输入雇主需求
    </div>
    """,
    unsafe_allow_html=True,
)


employer_request = st.text_area(
    "雇主需求",
    height=190,
    placeholder=(
        "例如：北京朝阳区住家，"
        "4岁女宝，老师独立房间，"
        "不用带睡，40岁以内，"
        "英语好，本科以上。"
    ),
)


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

    clear = st.button(
        "清除结果",
        use_container_width=True,
    )


if clear:

    for key in [
        "parsed",
        "results",
        "saved_request",
    ]:

        if key in st.session_state:

            del st.session_state[
                key
            ]

    st.rerun()


# ============================================================
# Match
# ============================================================

if start_matching:

    if not employer_request.strip():

        st.warning(
            "请输入雇主需求"
        )

    else:

        try:

            with st.spinner(
                "AI 正在解析并匹配..."
            ):

                parsed = (
                    parse_employer_requirement(
                        employer_request
                    )
                )

                results = (
                    run_matching(
                        teachers=teachers,
                        hard_requirements=(
                            parsed[
                                "hard_requirements"
                            ]
                        ),
                        preferred_requirements=(
                            parsed[
                                "preferred_requirements"
                            ]
                        ),
                        reference_requirements=(
                            parsed[
                                "reference_requirements"
                            ]
                        ),
                        top_n=TOP_N,
                    )
                )

                st.session_state[
                    "parsed"
                ] = parsed

                st.session_state[
                    "results"
                ] = results

                st.session_state[
                    "saved_request"
                ] = employer_request

        except Exception as error:

            st.error(
                "匹配过程中发生错误"
            )

            st.exception(
                error
            )


# ============================================================
# Parsed Result
# ============================================================

parsed = st.session_state.get(
    "parsed"
)

results = st.session_state.get(
    "results"
)


if parsed:

    st.divider()

    st.markdown(
        """
        <div class="section-title">
        2. AI 解析后的招聘条件
        </div>
        """,
        unsafe_allow_html=True,
    )

    hard_col, preferred_col, reference_col = st.columns(
        3
    )

    with hard_col:

        render_requirement_group(
            "必须条件",
            parsed[
                "hard_requirements"
            ],
        )

    with preferred_col:

        render_requirement_group(
            "偏好条件",
            parsed[
                "preferred_requirements"
            ],
        )

    with reference_col:

        render_requirement_group(
            "参考条件",
            parsed[
                "reference_requirements"
            ],
        )

    with st.expander(
        "查看 Gemini 原始解析"
    ):

        st.json(
            parsed[
                "raw_requirements"
            ]
        )


# ============================================================
# Results
# ============================================================

if results is not None:

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
            results
        )
    )

    metric1, metric2, metric3, metric4 = st.columns(
        4
    )

    with metric1:

        st.metric(
            "候选人数",
            summary[
                "total_results"
            ],
        )

    with metric2:

        st.metric(
            "符合全部硬条件",
            summary[
                "eligible_count"
            ],
        )

    with metric3:

        st.metric(
            "80%+",
            summary[
                "high_match_count"
            ],
        )

    with metric4:

        st.metric(
            "最高匹配度",
            f'{summary["best_score"]}%'
        )

    for index, result in enumerate(
        results,
        start=1,
    ):

        render_teacher_card(
            index,
            result,
        )


# ============================================================
# Footer
# ============================================================

st.divider()

st.caption(
    "Teacher Matching System V1.1 · "
    "Baserow + Gemini + Streamlit"
)
