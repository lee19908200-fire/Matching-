# ============================================================
# Teacher Matching System V1.1
# config.py
#
# Unified application configuration
# ============================================================

import streamlit as st


# ============================================================
# 1. Secrets
# ============================================================

try:
    BASEROW_TOKEN = st.secrets["BASEROW_TOKEN"]
except KeyError:
    BASEROW_TOKEN = None


try:
    TABLE_ID = int(
        st.secrets["TABLE_ID"]
    )
except (KeyError, TypeError, ValueError):
    TABLE_ID = None


try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None


try:
    GEMINI_MODEL = st.secrets["GEMINI_MODEL"]
except KeyError:
    GEMINI_MODEL = ""


# ============================================================
# 2. Baserow
# ============================================================

BASEROW_BASE_URL = "https://api.baserow.io"

BASEROW_PAGE_SIZE = 200

REQUEST_TIMEOUT = 30


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
# 3. Matching Settings
# ============================================================

TOP_N = 5


HARD_REQUIREMENT_WEIGHT = 0.70

PREFERRED_REQUIREMENT_WEIGHT = 0.20

REFERENCE_REQUIREMENT_WEIGHT = 0.10


# ============================================================
# 4. Field Groups
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
    "Night Care",
}


EXACT_TEXT_FIELDS = {
    "Nationality",
    "Current Country",
    "Visa Status",
}


SPECIAL_MATCH_FIELDS = {
    "Working City",
    "Minimum Years of Teaching",
    "Minimum Teacher Age",
    "Maximum Teacher Age",
    "Minimum Degree",
    "Private Room Provided",
    "Child Age",
}


ALLOWED_REQUIREMENT_FIELDS = (
    MULTI_SELECT_FIELDS
    | BOOLEAN_FIELDS
    | EXACT_TEXT_FIELDS
    | SPECIAL_MATCH_FIELDS
)


# ============================================================
# 5. Degree Ranking
# ============================================================

DEGREE_RANK = {
    "High School": 1,
    "Diploma": 2,
    "Associate Degree": 3,
    "Bachelor": 4,
    "Master": 5,
    "Doctorate": 6,
}


# ============================================================
# 6. China Cities
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
# 7. Standard Options
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

    "Minimum Degree": [
        "High School",
        "Diploma",
        "Associate Degree",
        "Bachelor",
        "Master",
        "Doctorate",
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
# 8. Validation
# ============================================================

def validate_config():

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

    return errors
