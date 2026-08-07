# ============================================================
# Teacher Matching System V1
# config.py
#
# 系统统一配置文件
# API Key / Token 从 Streamlit Secrets 读取
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


if TABLE_ID is not None:
    BASEROW_TABLE_URL = (
        f"{BASEROW_BASE_URL}"
        f"/api/database/rows/table/"
        f"{TABLE_ID}/"
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
# 2. Gemini Configuration
# ============================================================

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None


try:
    GEMINI_MODEL = st.secrets["GEMINI_MODEL"]
except KeyError:
    GEMINI_MODEL = ""


# ============================================================
# 3. General Settings
# ============================================================

TOP_N = 5

BASEROW_PAGE_SIZE = 200

REQUEST_TIMEOUT = 30


# ============================================================
# 4. Matching Weights
# ============================================================

HARD_REQUIREMENT_WEIGHT = 0.80

PREFERRED_REQUIREMENT_WEIGHT = 0.20


# ============================================================
# 5. Matching Fields
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
# 6. China Tier 1 Cities
# ============================================================

CHINA_TIER_1_CITIES = [
    "Beijing",
    "Shanghai",
    "Shenzhen",
    "Guangzhou",
]


# ============================================================
# 7. China Tier 2 / New Tier 1 Cities
# ============================================================

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


# ============================================================
# 8. Special Administrative Regions
# ============================================================

SPECIAL_ADMINISTRATIVE_REGIONS = [
    "Hong Kong",
    "Macau",
]


# ============================================================
# 9. International Cities
# ============================================================

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


# ============================================================
# 10. Working City Options
# ============================================================

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
# 11. Standard Database Options
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

    "Working City": WORKING_CITY_OPTIONS,
}


# ============================================================
# 12. Configuration Validation
# ============================================================

def validate_config():
    """
    检查系统运行所需配置。
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
