# ============================================================
# Teacher Matching System V1
# gemini_parser.py
#
# 负责：
# 1. 连接 Gemini
# 2. 自动寻找可用 Gemini 模型
# 3. 将雇主自然语言需求解析成 JSON
# 4. 区分 hard_requirements / preferred_requirements
# 5. 标准化城市、年龄、国籍、学科、课程、语言等
#
# 注意：
# - 不使用 Desired Position 做匹配
# - 不使用 Current City 做匹配
# - Family / Job Location -> Working City
# ============================================================


# ============================================================
# 1. Imports
# ============================================================

import json
import re

from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
)

from google import genai
from google.genai import types

import config


# ============================================================
# 2. Configuration
# ============================================================

GEMINI_API_KEY = getattr(
    config,
    "GEMINI_API_KEY",
    None,
)

GEMINI_MODEL = getattr(
    config,
    "GEMINI_MODEL",
    "",
)

ALLOWED_REQUIREMENT_FIELDS = getattr(
    config,
    "ALLOWED_REQUIREMENT_FIELDS",
    set(),
)

BOOLEAN_FIELDS = getattr(
    config,
    "BOOLEAN_FIELDS",
    set(),
)

MULTI_SELECT_FIELDS = getattr(
    config,
    "MULTI_SELECT_FIELDS",
    set(),
)

STANDARD_OPTIONS = getattr(
    config,
    "STANDARD_OPTIONS",
    {},
)

WORKING_CITY_OPTIONS = getattr(
    config,
    "WORKING_CITY_OPTIONS",
    [],
)


# ============================================================
# 3. Gemini Client
# ============================================================

if GEMINI_API_KEY:

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

else:

    gemini_client = None


# ============================================================
# 4. Runtime Model Cache
# ============================================================

_ACTIVE_MODEL = None


# ============================================================
# 5. Nationality Aliases
# ============================================================

NATIONALITY_ALIASES = {

    # United Kingdom
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "british": "United Kingdom",
    "britain": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "english": "United Kingdom",
    "英国": "United Kingdom",
    "英国籍": "United Kingdom",

    # United States
    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "american": "United States",
    "america": "United States",
    "美国": "United States",
    "美国籍": "United States",

    # Canada
    "canadian": "Canada",
    "加拿大": "Canada",
    "加拿大籍": "Canada",

    # Australia
    "australian": "Australia",
    "澳大利亚": "Australia",
    "澳洲": "Australia",
    "澳大利亚籍": "Australia",

    # New Zealand
    "new zealander": "New Zealand",
    "new zealand": "New Zealand",
    "新西兰": "New Zealand",

    # Ireland
    "irish": "Ireland",
    "爱尔兰": "Ireland",

    # South Africa
    "south african": "South Africa",
    "南非": "South Africa",

    # China
    "chinese": "China",
    "china": "China",
    "中国": "China",
    "中国籍": "China",

    # France
    "french": "France",
    "法国": "France",

    # Germany
    "german": "Germany",
    "德国": "Germany",

    # Spain
    "spanish": "Spain",
    "西班牙": "Spain",

    # Italy
    "italian": "Italy",
    "意大利": "Italy",
}


# ============================================================
# 6. Country Aliases
# ============================================================

COUNTRY_ALIASES = {

    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "英国": "United Kingdom",

    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "america": "United States",
    "美国": "United States",

    "canada": "Canada",
    "加拿大": "Canada",

    "australia": "Australia",
    "澳大利亚": "Australia",
    "澳洲": "Australia",

    "new zealand": "New Zealand",
    "新西兰": "New Zealand",

    "ireland": "Ireland",
    "爱尔兰": "Ireland",

    "south africa": "South Africa",
    "南非": "South Africa",

    "china": "China",
    "mainland china": "China",
    "mainland": "China",
    "prc": "China",
    "中国": "China",
    "中国大陆": "China",

    "hk": "Hong Kong",
    "hong kong": "Hong Kong",
    "hong kong sar": "Hong Kong",
    "香港": "Hong Kong",

    "macau": "Macau",
    "macao": "Macau",
    "澳门": "Macau",

    "singapore": "Singapore",
    "新加坡": "Singapore",

    "japan": "Japan",
    "日本": "Japan",

    "south korea": "South Korea",
    "korea": "South Korea",
    "韩国": "South Korea",

    "france": "France",
    "法国": "France",

    "germany": "Germany",
    "德国": "Germany",

    "spain": "Spain",
    "西班牙": "Spain",

    "italy": "Italy",
    "意大利": "Italy",
}


# ============================================================
# 7. Degree Aliases
# ============================================================

DEGREE_ALIASES = {

    "high school": "High School",
    "high school diploma": "High School",
    "secondary school": "High School",
    "高中": "High School",

    "diploma": "Diploma",
    "文凭": "Diploma",

    "associate": "Associate Degree",
    "associate degree": "Associate Degree",
    "associate's degree": "Associate Degree",
    "associates degree": "Associate Degree",

    "bachelor": "Bachelor",
    "bachelor degree": "Bachelor",
    "bachelor's degree": "Bachelor",
    "undergraduate": "Bachelor",
    "undergraduate degree": "Bachelor",
    "ba": "Bachelor",
    "b.a.": "Bachelor",
    "bsc": "Bachelor",
    "b.sc.": "Bachelor",
    "本科": "Bachelor",
    "学士": "Bachelor",
    "学士学位": "Bachelor",

    "master": "Master",
    "masters": "Master",
    "master degree": "Master",
    "master's degree": "Master",
    "masters degree": "Master",
    "postgraduate": "Master",
    "postgraduate degree": "Master",
    "ma": "Master",
    "m.a.": "Master",
    "msc": "Master",
    "m.sc.": "Master",
    "硕士": "Master",
    "研究生": "Master",

    "doctorate": "Doctorate",
    "doctoral": "Doctorate",
    "doctoral degree": "Doctorate",
    "phd": "Doctorate",
    "ph.d.": "Doctorate",
    "博士": "Doctorate",
}


# ============================================================
# 8. Subject Aliases
# ============================================================

SUBJECT_ALIASES = {

    # English
    "english": "English",
    "english language": "English",
    "英语": "English",

    # Mathematics
    "math": "Mathematics",
    "maths": "Mathematics",
    "mathematics": "Mathematics",
    "数学": "Mathematics",

    # Science
    "science": "Science",
    "general science": "Science",
    "科学": "Science",

    # Biology
    "biology": "Biology",
    "bio": "Biology",
    "生物": "Biology",

    # Chemistry
    "chemistry": "Chemistry",
    "chem": "Chemistry",
    "化学": "Chemistry",

    # Physics
    "physics": "Physics",
    "物理": "Physics",

    # History
    "history": "History",
    "历史": "History",

    # Geography
    "geography": "Geography",
    "地理": "Geography",

    # Economics
    "economics": "Economics",
    "经济": "Economics",
    "经济学": "Economics",

    # Business
    "business": "Business",
    "business studies": "Business",
    "商科": "Business",
    "商业": "Business",

    # Computer Science
    "computer science": "Computer Science",
    "computing": "Computer Science",
    "information technology": "Computer Science",
    "it": "Computer Science",
    "计算机": "Computer Science",
    "计算机科学": "Computer Science",

    # Art
    "art": "Art",
    "美术": "Art",

    # Music
    "music": "Music",
    "音乐": "Music",

    # Drama
    "drama": "Drama",
    "戏剧": "Drama",

    # PE
    "physical education": "PE / Sports",
    "sports": "PE / Sports",
    "sport": "PE / Sports",
    "pe": "PE / Sports",
    "体育": "PE / Sports",

    # Languages
    "languages": "Languages",
    "foreign languages": "Languages",
    "modern languages": "Languages",
    "语言": "Languages",

    # Early Years
    "early years": "Early Years",
    "early childhood": "Early Years",
    "early years education": "Early Years",
    "early childhood education": "Early Years",
    "preschool": "Early Years",
    "early learning": "Early Years",
    "nursery": "Early Years",
    "早教": "Early Years",
    "幼儿教育": "Early Years",
    "幼教": "Early Years",
    "学前教育": "Early Years",

    # Primary
    "primary": "Primary Education",
    "primary education": "Primary Education",
    "elementary": "Primary Education",
    "elementary education": "Primary Education",
    "小学": "Primary Education",
    "小学教育": "Primary Education",

    # Special Education
    "special needs": "Special Education",
    "special education": "Special Education",
    "sen": "Special Education",
    "特殊教育": "Special Education",
}


# ============================================================
# 9. Curriculum Aliases
# ============================================================

CURRICULUM_ALIASES = {

    "ib": "IB",
    "international baccalaureate": "IB",
    "ib curriculum": "IB",
    "ib programme": "IB",

    "igcse": "IGCSE",
    "international gcse": "IGCSE",
    "i-gcse": "IGCSE",

    "a-level": "A-Level",
    "a level": "A-Level",
    "a levels": "A-Level",
    "a-levels": "A-Level",

    "ap": "AP",
    "advanced placement": "AP",

    "sat": "SAT",

    "act": "ACT",

    "montessori": "Montessori",
    "蒙特梭利": "Montessori",

    "eyfs": "EYFS",
    "early years foundation stage": "EYFS",

    "reggio": "Reggio Emilia",
    "reggio emilia": "Reggio Emilia",
    "reggio emilia approach": "Reggio Emilia",

    "cambridge": "Cambridge",
    "cambridge curriculum": "Cambridge",
    "cambridge international": "Cambridge",

    "american": "American Curriculum",
    "american curriculum": "American Curriculum",
    "us curriculum": "American Curriculum",
    "american system": "American Curriculum",

    "local curriculum": "Local Curriculum",
    "national curriculum": "Local Curriculum",
    "local school curriculum": "Local Curriculum",
}


# ============================================================
# 10. Teaching Language Aliases
# ============================================================

LANGUAGE_ALIASES = {

    "english": "English",
    "english language": "English",
    "英语": "English",

    "mandarin": "Mandarin",
    "chinese": "Mandarin",
    "mandarin chinese": "Mandarin",
    "putonghua": "Mandarin",
    "普通话": "Mandarin",
    "中文": "Mandarin",

    "cantonese": "Cantonese",
    "cantonese chinese": "Cantonese",
    "粤语": "Cantonese",

    "french": "French",
    "french language": "French",
    "法语": "French",

    "german": "German",
    "german language": "German",
    "德语": "German",

    "spanish": "Spanish",
    "spanish language": "Spanish",
    "西班牙语": "Spanish",

    "italian": "Italian",
    "italian language": "Italian",
    "意大利语": "Italian",

    "japanese": "Japanese",
    "japanese language": "Japanese",
    "日语": "Japanese",

    "korean": "Korean",
    "korean language": "Korean",
    "韩语": "Korean",
}


# ============================================================
# 11. City Aliases
# ============================================================

CITY_ALIASES = {

    # Tier 1
    "北京": "Beijing",
    "北京市": "Beijing",
    "beijing city": "Beijing",

    "上海": "Shanghai",
    "上海市": "Shanghai",
    "shanghai city": "Shanghai",

    "深圳": "Shenzhen",
    "深圳市": "Shenzhen",

    "广州": "Guangzhou",
    "广州市": "Guangzhou",

    # China cities
    "成都": "Chengdu",
    "成都市": "Chengdu",

    "杭州": "Hangzhou",
    "杭州市": "Hangzhou",

    "重庆": "Chongqing",
    "重庆市": "Chongqing",

    "武汉": "Wuhan",
    "武汉市": "Wuhan",

    "南京": "Nanjing",
    "南京市": "Nanjing",

    "苏州": "Suzhou",
    "苏州市": "Suzhou",

    "西安": "Xi'an",
    "西安市": "Xi'an",
    "xian": "Xi'an",
    "xi an": "Xi'an",

    "天津": "Tianjin",
    "天津市": "Tianjin",

    "长沙": "Changsha",
    "长沙市": "Changsha",

    "郑州": "Zhengzhou",
    "郑州市": "Zhengzhou",

    "东莞": "Dongguan",
    "东莞市": "Dongguan",

    "宁波": "Ningbo",
    "宁波市": "Ningbo",

    "佛山": "Foshan",
    "佛山市": "Foshan",

    "合肥": "Hefei",
    "合肥市": "Hefei",

    "青岛": "Qingdao",
    "青岛市": "Qingdao",

    "昆明": "Kunming",
    "昆明市": "Kunming",

    "沈阳": "Shenyang",
    "沈阳市": "Shenyang",

    "济南": "Jinan",
    "济南市": "Jinan",

    "厦门": "Xiamen",
    "厦门市": "Xiamen",

    "福州": "Fuzhou",
    "福州市": "Fuzhou",

    "大连": "Dalian",
    "大连市": "Dalian",

    "哈尔滨": "Harbin",
    "哈尔滨市": "Harbin",

    "长春": "Changchun",
    "长春市": "Changchun",

    "石家庄": "Shijiazhuang",
    "石家庄市": "Shijiazhuang",

    "南昌": "Nanchang",
    "南昌市": "Nanchang",

    "南宁": "Nanning",
    "南宁市": "Nanning",

    "贵阳": "Guiyang",
    "贵阳市": "Guiyang",

    "太原": "Taiyuan",
    "太原市": "Taiyuan",

    "无锡": "Wuxi",
    "无锡市": "Wuxi",

    "温州": "Wenzhou",
    "温州市": "Wenzhou",

    "珠海": "Zhuhai",
    "珠海市": "Zhuhai",

    "三亚": "Sanya",
    "三亚市": "Sanya",

    "海口": "Haikou",
    "海口市": "Haikou",

    # SAR
    "香港": "Hong Kong",
    "香港特别行政区": "Hong Kong",
    "hk": "Hong Kong",
    "hong kong sar": "Hong Kong",

    "澳门": "Macau",
    "澳门特别行政区": "Macau",
    "macao": "Macau",

    # International
    "新加坡": "Singapore",

    "伦敦": "London",
    "悉尼": "Sydney",
    "墨尔本": "Melbourne",
    "多伦多": "Toronto",
    "温哥华": "Vancouver",
    "纽约": "New York",
    "洛杉矶": "Los Angeles",
    "迪拜": "Dubai",
    "巴黎": "Paris",
    "东京": "Tokyo",
    "首尔": "Seoul",

    # Any city
    "任何城市": "Any City",
    "任意城市": "Any City",
    "全国": "Any City",
    "全国均可": "Any City",
    "不限城市": "Any City",
    "城市不限": "Any City",

    "anywhere": "Any City",
    "any location": "Any City",
    "any city": "Any City",
}


# ============================================================
# 12. Generic Text Normalization
# ============================================================

def normalize_text(
    value: Any
) -> str:

    if value is None:
        return ""

    text = (
        str(value)
        .strip()
        .lower()
    )

    text = text.replace(
        "–",
        "-"
    )

    text = text.replace(
        "—",
        "-"
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


# ============================================================
# 13. Ensure List
# ============================================================

def ensure_list(
    value: Any
) -> List[Any]:

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


# ============================================================
# 14. Normalize Model Name
# ============================================================

def normalize_model_name(
    model_name: Any
) -> str:

    if not model_name:
        return ""

    model_name = (
        str(model_name)
        .strip()
    )

    if model_name.startswith(
        "models/"
    ):

        model_name = (
            model_name[
                len("models/"):
            ]
        )

    return model_name


# ============================================================
# 15. List GenerateContent Models
# ============================================================

def list_generate_content_models(
    limit: int = 100
) -> List[str]:
    """
    返回当前 Gemini API Key 可以访问、
    并支持 generateContent 的模型。
    """

    if gemini_client is None:
        return []

    model_names = []

    try:

        for model in (
            gemini_client
            .models
            .list()
        ):

            actions = (
                getattr(
                    model,
                    "supported_actions",
                    None,
                )
                or []
            )

            if (
                "generateContent"
                not in actions
            ):
                continue

            name = normalize_model_name(
                getattr(
                    model,
                    "name",
                    "",
                )
            )

            if (
                name
                and name
                not in model_names
            ):

                model_names.append(
                    name
                )

            if (
                len(model_names)
                >= limit
            ):
                break

    except Exception:

        return []

    return model_names


# ============================================================
# 16. Resolve Gemini Model
# ============================================================

def resolve_gemini_model(
    force_refresh: bool = False
) -> str:
    """
    自动寻找当前 API Key 可使用的模型。

    优先级：

    1. Streamlit Secrets 中的 GEMINI_MODEL
    2. gemini-3.6-flash
    3. gemini-3.5-flash
    4. API 返回的其他 Flash generateContent model
    5. API 返回的第一个 generateContent model
    """

    global _ACTIVE_MODEL

    if (
        _ACTIVE_MODEL
        and not force_refresh
    ):
        return _ACTIVE_MODEL

    configured_model = (
        normalize_model_name(
            GEMINI_MODEL
        )
    )

    available_models = (
        list_generate_content_models()
    )

    # --------------------------------------------------------
    # 如果 models.list 成功
    # --------------------------------------------------------

    if available_models:

        preferred_candidates = [
            configured_model,
            "gemini-3.6-flash",
            "gemini-3.5-flash",
        ]

        for candidate in (
            preferred_candidates
        ):

            if (
                candidate
                and candidate
                in available_models
            ):

                _ACTIVE_MODEL = (
                    candidate
                )

                return (
                    _ACTIVE_MODEL
                )

        # 找任意 flash
        for model_name in (
            available_models
        ):

            if "flash" in (
                model_name.lower()
            ):

                _ACTIVE_MODEL = (
                    model_name
                )

                return (
                    _ACTIVE_MODEL
                )

        # 最后使用第一个
        _ACTIVE_MODEL = (
            available_models[0]
        )

        return (
            _ACTIVE_MODEL
        )

    # --------------------------------------------------------
    # 如果 models.list 因 API / SDK 限制失败
    # --------------------------------------------------------

    if configured_model:

        _ACTIVE_MODEL = (
            configured_model
        )

        return (
            _ACTIVE_MODEL
        )

    _ACTIVE_MODEL = (
        "gemini-3.6-flash"
    )

    return (
        _ACTIVE_MODEL
    )


# ============================================================
# 17. Standard Option Lookup
# ============================================================

def find_standard_option(
    field: str,
    value: Any,
) -> Optional[str]:

    normalized_value = (
        normalize_text(
            value
        )
    )

    for option in (
        STANDARD_OPTIONS.get(
            field,
            [],
        )
    ):

        if (
            normalize_text(
                option
            )
            ==
            normalized_value
        ):

            return option

    return None


# ============================================================
# 18. Number / Age Parsing
# ============================================================

def normalize_number(
    value: Any
) -> Optional[float]:

    if value is None:
        return None

    if isinstance(
        value,
        (
            int,
            float,
        ),
    ):

        return float(
            value
        )

    text = (
        str(value)
        .strip()
    )

    # --------------------------------------------------------
    # Months
    # --------------------------------------------------------

    month_match = re.search(
        r"(\d+(?:\.\d+)?)\s*个月",
        text,
    )

    if month_match:

        months = float(
            month_match.group(1)
        )

        return round(
            months / 12,
            2,
        )

    english_month_match = re.search(
        r"(\d+(?:\.\d+)?)\s*months?",
        text,
        re.IGNORECASE,
    )

    if english_month_match:

        months = float(
            english_month_match.group(1)
        )

        return round(
            months / 12,
            2,
        )

    # --------------------------------------------------------
    # Chinese ages
    # --------------------------------------------------------

    chinese_age_map = {

        "半岁": 0.5,

        "一岁半": 1.5,
        "1岁半": 1.5,

        "两岁半": 2.5,
        "2岁半": 2.5,

        "三岁半": 3.5,
        "3岁半": 3.5,

        "四岁半": 4.5,
        "4岁半": 4.5,

        "一岁": 1.0,
        "两岁": 2.0,
        "三岁": 3.0,
        "四岁": 4.0,
        "五岁": 5.0,
        "六岁": 6.0,
        "七岁": 7.0,
        "八岁": 8.0,
        "九岁": 9.0,
        "十岁": 10.0,
        "十一岁": 11.0,
        "十二岁": 12.0,
        "十三岁": 13.0,
        "十四岁": 14.0,
        "十五岁": 15.0,
        "十六岁": 16.0,
        "十七岁": 17.0,
        "十八岁": 18.0,
    }

    for (
        expression,
        number,
    ) in (
        chinese_age_map.items()
    ):

        if expression in text:

            return float(
                number
            )

    # --------------------------------------------------------
    # Normal number
    # --------------------------------------------------------

    number_match = re.search(
        r"\d+(?:\.\d+)?",
        text,
    )

    if not number_match:
        return None

    return float(
        number_match.group(0)
    )


# ============================================================
# 19. Boolean Normalization
# ============================================================

def normalize_boolean(
    value: Any
) -> Optional[bool]:

    if isinstance(
        value,
        bool,
    ):

        return value

    normalized_value = (
        normalize_text(
            value
        )
    )

    true_values = {

        "true",
        "yes",
        "y",
        "1",

        "required",
        "must",
        "needed",
        "essential",

        "是",
        "需要",
        "必须",
        "要求",
        "可以",
        "愿意",
        "有",
    }

    false_values = {

        "false",
        "no",
        "n",
        "0",

        "not required",
        "not needed",

        "否",
        "不需要",
        "不要求",
        "不能",
        "不愿意",
        "没有",
    }

    if (
        normalized_value
        in true_values
    ):

        return True

    if (
        normalized_value
        in false_values
    ):

        return False

    return None


# ============================================================
# 20. Single Option Normalization
# ============================================================

def normalize_single_option(
    field: str,
    value: Any,
) -> Optional[str]:

    if value is None:
        return None

    # Exact standard option first
    direct_match = (
        find_standard_option(
            field,
            value,
        )
    )

    if direct_match:
        return direct_match

    alias_key = (
        normalize_text(
            value
        )
    )

    # --------------------------------------------------------
    # Nationality
    # --------------------------------------------------------

    if field == "Nationality":

        return (
            NATIONALITY_ALIASES.get(
                alias_key
            )
        )

    # --------------------------------------------------------
    # Current Country
    # --------------------------------------------------------

    if (
        field
        ==
        "Current Country"
    ):

        return (
            COUNTRY_ALIASES.get(
                alias_key,
                str(value).strip(),
            )
        )

    # --------------------------------------------------------
    # Highest Degree
    # --------------------------------------------------------

    if (
        field
        ==
        "Highest Degree"
    ):

        return (
            DEGREE_ALIASES.get(
                alias_key
            )
        )

    # --------------------------------------------------------
    # Working City
    # --------------------------------------------------------

    if (
        field
        ==
        "Working City"
    ):

        city_value = (
            CITY_ALIASES.get(
                alias_key
            )
        )

        if city_value:

            return city_value

        # English exact match
        for city in (
            WORKING_CITY_OPTIONS
        ):

            if (
                normalize_text(
                    city
                )
                ==
                alias_key
            ):

                return city

        # Preserve unknown city rather than deleting it.
        return (
            str(value)
            .strip()
        )

    # --------------------------------------------------------
    # Visa Status
    # --------------------------------------------------------

    if (
        field
        ==
        "Visa Status"
    ):

        return (
            str(value)
            .strip()
        )

    return None


# ============================================================
# 21. Multiple Select Option Normalization
# ============================================================

def normalize_multi_option(
    field: str,
    value: Any,
) -> Optional[str]:

    if value is None:
        return None

    direct_match = (
        find_standard_option(
            field,
            value,
        )
    )

    if direct_match:

        return direct_match

    alias_key = (
        normalize_text(
            value
        )
    )

    # --------------------------------------------------------
    # Subjects
    # --------------------------------------------------------

    if field == "Subjects":

        return (
            SUBJECT_ALIASES.get(
                alias_key
            )
        )

    # --------------------------------------------------------
    # Curriculum
    # --------------------------------------------------------

    if field == "Curriculum":

        return (
            CURRICULUM_ALIASES.get(
                alias_key
            )
        )

    # --------------------------------------------------------
    # Teaching Languages
    # --------------------------------------------------------

    if (
        field
        ==
        "Teaching Languages"
    ):

        return (
            LANGUAGE_ALIASES.get(
                alias_key
            )
        )

    # --------------------------------------------------------
    # Visa / Work Authorization Countries
    # --------------------------------------------------------

    if (
        field
        ==
        "Visa / Work Authorization Countries"
    ):

        country_value = (
            COUNTRY_ALIASES.get(
                alias_key
            )
        )

        if country_value:

            return (
                country_value
            )

        # Preserve exact standard option
        standard_country = (
            find_standard_option(
                field,
                value,
            )
        )

        if standard_country:

            return (
                standard_country
            )

    return None


# ============================================================
# 22. Requirement Field Normalization
# ============================================================

def normalize_requirement_field(
    field: str,
    value: Any,
) -> Tuple[
    Any,
    List[str],
]:

    warnings = []

    # --------------------------------------------------------
    # Unsupported fields
    # --------------------------------------------------------

    if (
        ALLOWED_REQUIREMENT_FIELDS
        and
        field
        not in
        ALLOWED_REQUIREMENT_FIELDS
    ):

        warnings.append(
            f"忽略未参与匹配字段：{field}"
        )

        return (
            None,
            warnings,
        )

    # --------------------------------------------------------
    # Numeric fields
    # --------------------------------------------------------

    if field in {

        "Child Age",
        "Minimum Years of Teaching",

    }:

        normalized_value = (
            normalize_number(
                value
            )
        )

        if (
            normalized_value
            is None
        ):

            warnings.append(
                f"无法识别数字字段 "
                f"{field}: {value}"
            )

        return (
            normalized_value,
            warnings,
        )

    # --------------------------------------------------------
    # Boolean fields
    # --------------------------------------------------------

    if (
        field
        in
        BOOLEAN_FIELDS
    ):

        normalized_value = (
            normalize_boolean(
                value
            )
        )

        if (
            normalized_value
            is None
        ):

            warnings.append(
                f"无法识别 Yes/No 字段 "
                f"{field}: {value}"
            )

        return (
            normalized_value,
            warnings,
        )

    # --------------------------------------------------------
    # Multiple select fields
    # --------------------------------------------------------

    if (
        field
        in
        MULTI_SELECT_FIELDS
    ):

        normalized_values = []

        for raw_value in (
            ensure_list(
                value
            )
        ):

            normalized_item = (
                normalize_multi_option(
                    field,
                    raw_value,
                )
            )

            if (
                normalized_item
                is None
            ):

                warnings.append(
                    f"无法标准化 "
                    f"{field}: {raw_value}"
                )

                continue

            if (
                normalized_item
                not in
                normalized_values
            ):

                normalized_values.append(
                    normalized_item
                )

        if not normalized_values:

            return (
                None,
                warnings,
            )

        return (
            normalized_values,
            warnings,
        )

    # --------------------------------------------------------
    # Single fields
    # --------------------------------------------------------

    normalized_value = (
        normalize_single_option(
            field,
            value,
        )
    )

    if (
        normalized_value
        is None
    ):

        warnings.append(
            f"无法标准化 "
            f"{field}: {value}"
        )

    return (
        normalized_value,
        warnings,
    )


# ============================================================
# 23. Requirement Group Normalization
# ============================================================

def normalize_requirement_group(
    requirements: Dict[
        str,
        Any,
    ]
) -> Tuple[
    Dict[str, Any],
    List[str],
]:

    normalized_requirements = {}

    warnings = []

    if not isinstance(
        requirements,
        dict,
    ):

        return (
            {},
            [
                "Requirements 格式错误："
                "Gemini 返回值不是 dictionary。"
            ],
        )

    for (
        field,
        value,
    ) in (
        requirements.items()
    ):

        # ----------------------------------------------------
        # Never match these fields
        # ----------------------------------------------------

        if field in {

            "Desired Position",
            "Current City",
            "Age Groups",

        }:

            warnings.append(
                f"{field} 仅展示或已停用，"
                "不参与匹配。"
            )

            continue

        if value is None:
            continue

        if value == "":
            continue

        if value == []:
            continue

        (
            normalized_value,
            field_warnings,
        ) = (
            normalize_requirement_field(
                field,
                value,
            )
        )

        warnings.extend(
            field_warnings
        )

        if (
            normalized_value
            is None
        ):

            continue

        normalized_requirements[
            field
        ] = (
            normalized_value
        )

    return (
        normalized_requirements,
        warnings,
    )


# ============================================================
# 24. Clean Gemini JSON
# ============================================================

def clean_gemini_json(
    text: str
) -> str:

    if not text:

        return ""

    cleaned_text = (
        str(text)
        .strip()
    )

    cleaned_text = (
        cleaned_text
        .replace(
            "```json",
            "",
        )
        .replace(
            "```JSON",
            "",
        )
        .replace(
            "```",
            "",
        )
        .strip()
    )

    json_match = re.search(
        r"\{.*\}",
        cleaned_text,
        re.DOTALL,
    )

    if json_match:

        return (
            json_match.group(0)
        )

    return (
        cleaned_text
    )


# ============================================================
# 25. Prompt Builder
# ============================================================

def build_requirement_prompt(
    employer_request: str
) -> str:

    city_options_json = (
        json.dumps(
            WORKING_CITY_OPTIONS,
            ensure_ascii=False,
            indent=2,
        )
    )

    standard_options_json = (
        json.dumps(
            STANDARD_OPTIONS,
            ensure_ascii=False,
            indent=2,
        )
    )

    return f"""
You are an expert recruitment requirement parser for an
international private teacher, tutor, nanny educator,
governess and family education recruitment company.

Your task is to convert the employer request into structured
matching requirements.

Return ONLY valid JSON.

The exact top-level JSON structure MUST be:

{{
  "hard_requirements": {{}},
  "preferred_requirements": {{}}
}}

============================================================
ALLOWED MATCHING FIELDS
============================================================

Nationality

Current Country

Visa Status

Visa / Work Authorization Countries

Highest Degree

Minimum Years of Teaching

Child Age

Working City

Subjects

Curriculum

Teaching Languages

SEN Experience

International School Experience

Private Tutoring Experience

Live-in

Willing to Travel

Driving

Nanny Educator Experience


============================================================
FIELDS YOU MUST NEVER RETURN
============================================================

Current City

Desired Position

Age Groups


============================================================
RULE 1 — JOB LOCATION
============================================================

The employer's location, family location or job location must
be mapped to:

Working City

NEVER map family location to Current City.

Examples:

北京家庭
->
"Working City": "Beijing"

杭州家庭
->
"Working City": "Hangzhou"

工作地点上海
->
"Working City": "Shanghai"


============================================================
RULE 2 — JOB TITLES
============================================================

Do NOT convert job titles into matching requirements.

Ignore job titles such as:

Governor
Governess
Private Tutor
Tutor
Nanny
Nanny Educator
Teacher
Homeschool Teacher
Subject Specialist
家庭教师
家庭老师
育儿师
育儿老师
住家老师
住家教师


============================================================
RULE 3 — CHILD AGE
============================================================

If the employer states a child's age, return:

"Child Age": number

Examples:

20个月
->
"Child Age": 1.67

18个月
->
"Child Age": 1.5

一岁半
->
"Child Age": 1.5

2岁
->
"Child Age": 2

10岁
->
"Child Age": 10

Do NOT use Age Groups for the child's age.


============================================================
RULE 4 — WORKING CITY
============================================================

Whenever possible use one of these standardized values:

{city_options_json}


============================================================
RULE 5 — MULTIPLE VALUE FIELDS
============================================================

These fields MUST always be JSON arrays:

Subjects

Curriculum

Teaching Languages

Visa / Work Authorization Countries

Correct:

"Subjects": [
  "English",
  "Mathematics"
]

Incorrect:

"Subjects": "English"


============================================================
RULE 6 — BOOLEAN FIELDS
============================================================

Use JSON true or false for:

SEN Experience

International School Experience

Private Tutoring Experience

Live-in

Willing to Travel

Driving

Nanny Educator Experience


Examples:

住家
->
"Live-in": true

会开车
->
"Driving": true

有SEN经验
->
"SEN Experience": true

有育儿经验
->
"Nanny Educator Experience": true


============================================================
RULE 7 — HARD REQUIREMENTS
============================================================

Requirements expressed using words such as:

must
required
essential
mandatory
need
needs

必须
要求
需要
一定要
一定需要
必须有

should normally belong in:

hard_requirements


============================================================
RULE 8 — PREFERRED REQUIREMENTS
============================================================

Requirements expressed using words such as:

preferred
preferably
ideally
nice to have
would be good

最好
优先
希望
有...更好
如果有...更好

should normally belong in:

preferred_requirements


============================================================
RULE 9 — MINIMUM EXPERIENCE
============================================================

Examples:

至少5年教学经验

->
"Minimum Years of Teaching": 5


5年以上经验

->
"Minimum Years of Teaching": 5


最好有10年以上经验

->
preferred_requirements:
{{
  "Minimum Years of Teaching": 10
}}


============================================================
RULE 10 — EARLY YEARS
============================================================

Terms including:

早教
幼教
幼儿教育
学前教育
Early Years
Early Childhood Education

may be represented as:

"Subjects": [
  "Early Years"
]


============================================================
RULE 11 — DO NOT INVENT
============================================================

Never invent a requirement that was not stated or clearly
implied by the employer.

Do not assume:

nationality

degree

visa

driving

live-in

curriculum

language

experience

school background


============================================================
STANDARD DATABASE VALUES
============================================================

{standard_options_json}


============================================================
EMPLOYER REQUEST
============================================================

{employer_request}


Return ONLY JSON.
"""


# ============================================================
# 26. Raw Gemini Generate Function
# ============================================================

def generate_requirement_json(
    employer_request: str
) -> Tuple[
    Dict[str, Any],
    str,
]:

    if gemini_client is None:

        raise RuntimeError(
            "Gemini API Key 未配置。"
        )

    if not employer_request:

        raise ValueError(
            "雇主需求不能为空。"
        )

    model_name = (
        resolve_gemini_model()
    )

    prompt = (
        build_requirement_prompt(
            employer_request
        )
    )

    try:

        response = (
            gemini_client
            .models
            .generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type=(
                        "application/json"
                    ),
                ),
            )
        )

    except Exception as first_error:

        # ----------------------------------------------------
        # Model may have become unavailable.
        # Refresh model list and retry once.
        # ----------------------------------------------------

        refreshed_model = (
            resolve_gemini_model(
                force_refresh=True
            )
        )

        if (
            refreshed_model
            ==
            model_name
        ):

            raise RuntimeError(
                "Gemini 请求失败。\n"
                f"模型：{model_name}\n"
                f"错误：{first_error}"
            ) from first_error

        try:

            response = (
                gemini_client
                .models
                .generate_content(
                    model=(
                        refreshed_model
                    ),
                    contents=prompt,
                    config=(
                        types.GenerateContentConfig(
                            response_mime_type=(
                                "application/json"
                            ),
                        )
                    ),
                )
            )

            model_name = (
                refreshed_model
            )

        except Exception as second_error:

            raise RuntimeError(
                "Gemini 请求失败。\n"
                f"第一次模型："
                f"{model_name}\n"
                f"第二次模型："
                f"{refreshed_model}\n"
                f"错误："
                f"{second_error}"
            ) from second_error

    response_text = getattr(
        response,
        "text",
        None,
    )

    if not response_text:

        raise RuntimeError(
            "Gemini 已返回响应，"
            "但没有生成文本内容。"
        )

    cleaned_text = (
        clean_gemini_json(
            response_text
        )
    )

    try:

        parsed_json = (
            json.loads(
                cleaned_text
            )
        )

    except json.JSONDecodeError as error:

        raise RuntimeError(
            "Gemini 返回内容不是有效 JSON。\n"
            f"模型：{model_name}\n"
            f"返回内容：{response_text}"
        ) from error

    return (
        parsed_json,
        model_name,
    )


# ============================================================
# 27. Main Employer Requirement Parser
# ============================================================

def parse_employer_requirement(
    employer_request: str
) -> Dict[str, Any]:

    cleaned_request = (
        str(
            employer_request
        )
        .strip()
    )

    if not cleaned_request:

        raise ValueError(
            "请输入雇主需求。"
        )

    (
        raw_requirements,
        model_used,
    ) = (
        generate_requirement_json(
            cleaned_request
        )
    )

    hard_raw = (
        raw_requirements.get(
            "hard_requirements",
            {},
        )
    )

    preferred_raw = (
        raw_requirements.get(
            "preferred_requirements",
            {},
        )
    )

    (
        hard_requirements,
        hard_warnings,
    ) = (
        normalize_requirement_group(
            hard_raw
        )
    )

    (
        preferred_requirements,
        preferred_warnings,
    ) = (
        normalize_requirement_group(
            preferred_raw
        )
    )

    warnings = (
        hard_warnings
        +
        preferred_warnings
    )

    return {

        "original_request": (
            cleaned_request
        ),

        "model_used": (
            model_used
        ),

        "raw_requirements": (
            raw_requirements
        ),

        "hard_requirements": (
            hard_requirements
        ),

        "preferred_requirements": (
            preferred_requirements
        ),

        "warnings": (
            warnings
        ),
    }


# ============================================================
# 28. Gemini Connection Health Check
# ============================================================

def check_gemini_connection() -> Dict[str, Any]:
    """
    Streamlit sidebar 使用。

    检查：
    1. API Key 是否存在
    2. 可以访问哪些 generateContent 模型
    3. 选择一个实际可用模型
    4. 发一个极小的测试请求
    """

    if not GEMINI_API_KEY:

        return {

            "success": False,

            "message": (
                "GEMINI_API_KEY 未配置。"
            ),

            "model": None,

            "available_models": [],
        }

    if gemini_client is None:

        return {

            "success": False,

            "message": (
                "无法创建 Gemini Client。"
            ),

            "model": None,

            "available_models": [],
        }

    available_models = (
        list_generate_content_models(
            limit=30
        )
    )

    try:

        model_name = (
            resolve_gemini_model(
                force_refresh=True
            )
        )

        response = (
            gemini_client
            .models
            .generate_content(
                model=model_name,
                contents=(
                    "Reply with exactly the word OK."
                ),
            )
        )

        response_text = (
            getattr(
                response,
                "text",
                "",
            )
            or ""
        )

        if not response_text:

            return {

                "success": False,

                "message": (
                    "Gemini API 可以访问，"
                    "但测试请求没有返回文本。"
                ),

                "model": (
                    model_name
                ),

                "available_models": (
                    available_models
                ),
            }

        return {

            "success": True,

            "message": (
                f"Gemini 已连接 · "
                f"{model_name}"
            ),

            "model": (
                model_name
            ),

            "available_models": (
                available_models
            ),
        }

    except Exception as error:

        return {

            "success": False,

            "message": (
                "Gemini 连接失败："
                f"{error}"
            ),

            "model": None,

            "available_models": (
                available_models
            ),
        }


# ============================================================
# 29. Optional Diagnostic Function
# ============================================================

def get_gemini_diagnostics() -> Dict[str, Any]:
    """
    调试时使用。

    不会返回 API Key。
    """

    available_models = (
        list_generate_content_models(
            limit=50
        )
    )

    try:

        active_model = (
            resolve_gemini_model(
                force_refresh=True
            )
        )

    except Exception:

        active_model = None

    return {

        "api_key_configured": (
            bool(
                GEMINI_API_KEY
            )
        ),

        "configured_model": (
            normalize_model_name(
                GEMINI_MODEL
            )
        ),

        "active_model": (
            active_model
        ),

        "available_models": (
            available_models
        ),
    }
