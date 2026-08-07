# ============================================================
# Teacher Matching System V1
# config.py
#
# 系统统一配置文件
# 不在这里直接保存 API Key。
# API Key 将通过 Streamlit Secrets 安全读取。
# ============================================================

import streamlit as st


# ============================================================
# 1. Baserow Configuration
# ============================================================

try:
    BASEROW_TOKEN = st.secrets["BASEROW_TOKEN"]
except KeyError:
    BASEROW_TOKEN = None


try:
    TABLE_ID = int(st.secrets["TABLE_ID"])
except (KeyError, TypeError, ValueError):
    TABLE_ID = None


BASEROW_BASE_URL = "https://api.baserow.io"


def get_baserow_table_url():
    """
    返回 Teachers 表 API 地址。
    """

    if TABLE_ID is None:
        return None

    return (
        f"{BASEROW_BASE_URL}"
        f"/api/database/rows/table/"
        f"{TABLE_ID}/"
    )


BASEROW_TABLE_URL = get_baserow_table_url()


def get_baserow_headers():
    """
    返回 Baserow API Headers。
    """

    if not BASEROW_TOKEN:
        return {}

    return {
        "Authorization": (
            f"Token {BASEROW_TOKEN}"
        ),
        "Content-Type": "application/json",
    }


# ============================================================
# 2. Gemini Configuration
# ============================================================

try:
    GEMINI_API_KEY = st.secrets[
        "GEMINI_API_KEY"
    ]
except KeyError:
    GEMINI_API_KEY = None


try:
    GEMINI_MODEL = st.secrets[
        "GEMINI_MODEL"
    ]
except KeyError:
    # 实际部署时建议在 Streamlit Secrets
    # 明确填写当前可用模型。
    GEMINI_MODEL = ""


# ============================================================
# 3. Matching Configuration
# ============================================================

TOP_N = 5

BASEROW_PAGE_SIZE = 200

REQUEST_TIMEOUT = 30


# 硬条件与偏好条件的评分权重
HARD_REQUIREMENT_WEIGHT = 0.80

PREFERRED_REQUIREMENT_WEIGHT = 0.20


# ============================================================
# 4. Matching Fields
#
# Current City：
# 只展示，不参与匹配。
#
# Desired Position：
# 只展示，不参与匹配。
#
# Governor / Governess：
# 不作为职位筛选条件。
# ============================================================

MULTI_SELECT_FIELDS = {
    "Subjects",
    "Curriculum",
    "Teaching Languages",
    "Visa / Work Authorization Countries",
}


BOOLEAN_FIELDS = {
    "SEN Experience",
    "International School Experience",
    "Private Tutoring Experience",
    "Live-in",
    "Willing to Travel",
    "Driving",
    "Nanny Educator Experience",
}


EXACT_TEXT_FIELDS = {
    "Nationality",
    "Current Country",
    "Visa Status",
    "Highest Degree",
}


SPECIAL_MATCH_FIELDS = {
    "Working City",
    "Child Age",
    "Minimum Years of Teaching",
}


ALLOWED_REQUIREMENT_FIELDS = (
    MULTI_SELECT_FIELDS
    | BOOLEAN_FIELDS
    | EXACT_TEXT_FIELDS
    | SPECIAL_MATCH_FIELDS
)


# ============================================================
# 5. China Working Cities
# ============================================================

CHINA_TIER_1_CITIES = [
    "Beijing",
    "Shanghai",
    "Shenzhen",
    "Guangzhou",
]


CHINA_TIER_2_AND_NEW_TIER_1_CITIES = [
    "Chengdu",
    "Hangzhou",
    "Chongqing",
    "Wuhan",
    "Nanjing",
    "Suzhou",
    "Xi'an",
    "Tianjin",
    "Changsha",
    "Zhengzhou",
    "Dongguan",
    "Ningbo",
    "Foshan",
    "Hefei",
    "Qingdao",
    "Kunming",
    "Shenyang",
    "Jinan",
    "Xiamen",
    "Fuzhou",
    "Dalian",
    "Harbin",
    "Changchun",
    "Shijiazhuang",
    "Nanchang",
    "Nanning",
    "Guiyang",
    "Taiyuan",
    "Wuxi",
    "Wenzhou",
    "Zhuhai",
    "Sanya",
    "Haikou",
]


SPECIAL_ADMINISTRATIVE_REGIONS = [
    "Hong Kong",
    "Macau",
]


INTERNATIONAL_CITIES = [
    "Singapore",
    "London",
    "Sydney",
    "Melbourne",
    "Toronto",
    "Vancouver",
    "New York",
    "Los Angeles",
    "Dubai",
    "Paris",
    "Tokyo",
    "Seoul",
]


WORKING_CITY_OPTIONS = (
    CHINA_TIER_1_CITIES
    + CHINA_TIER_2_AND_NEW_TIER_1_CITIES
    + SPECIAL_ADMINISTRATIVE_REGIONS
    + INTERNATIONAL_CITIES
    + [
        "Any City",
        "Other",
    ]
)


# ============================================================
# 6. Standard Database Options
# ============================================================

STANDARD_OPTIONS = {
    "Nationality": [
        "United Kingdom",
        "United States",
        "Canada",
        "Australia",
        "New Zealand",
        "Ireland",
        "South Africa",
        "China",
        "France",
        "Germany",
        "Spain",
        "Italy",
        "Other",
        "Unknown",
    ],

    "Current Country": [
        "China",
        "United Kingdom",
        "United States",
        "Canada",
        "Australia",
        "New Zealand",
        "Singapore",
        "Hong Kong",
        "Japan",
        "South Korea",
        "France",
        "Germany",
        "Spain",
        "Italy",
        "Ireland",
        "South Africa",
        "Other",
        "Unknown",
    ],

    "Highest Degree": [
        "High School",
        "Diploma",
        "Associate Degree",
        "Bachelor",
        "Master",
        "Doctorate",
        "Other",
        "Unknown",
    ],

    "Subjects": [
        "English",
        "Mathematics",
        "Science",
        "Biology",
        "Chemistry",
        "Physics",
        "History",
        "Geography",
        "Economics",
        "Business",
        "Computer Science",
        "Art",
        "Music",
        "Drama",
        "PE / Sports",
        "Languages",
        "Early Years",
        "Primary Education",
        "Special Education",
    ],

    "Curriculum": [
        "IB",
        "IGCSE",
        "A-Level",
        "AP",
        "SAT",
        "ACT",
        "Montessori",
        "EYFS",
        "Reggio Emilia",
        "Cambridge",
        "American Curriculum",
        "Local Curriculum",
    ],

    "Teaching Languages": [
        "English",
        "Mandarin",
        "Cantonese",
        "French",
        "German",
        "Spanish",
        "Italian",
        "Japanese",
        "Korean",
        "Other",
    ],

    "Visa / Work Authorization Countries": [
        "China",
        "United Kingdom",
        "United States",
        "Canada",
        "Australia",
        "New Zealand",
        "Singapore",
        "Hong Kong",
        "Japan",
        "South Korea",
        "France",
        "Germany",
        "Spain",
        "Italy",
        "Ireland",
        "South Africa",
        "Other",
        "Unknown",
    ],

    "Working City": (
        WORKING_CITY_OPTIONS
    ),
}


# ============================================================
# 7. Configuration Validation
# ============================================================

def validate_config():
    """
    检查系统是否已经配置好运行所需参数。

    返回：
    errors: list[str]
    """

    errors = []

    if not BASEROW_TOKEN:
        errors.append(
            "缺少 BASEROW_TOKEN"
        )

    if TABLE_ID is None:
        errors.append(
            "缺少或无效的 TABLE_ID"
        )

    if not GEMINI_API_KEY:
        errors.append(
            "缺少 GEMINI_API_KEY"
        )

    if not GEMINI_MODEL:
        errors.append(
            "缺少 GEMINI_MODEL"
        )

    return errors
