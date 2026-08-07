# ============================================================
# Teacher Matching System V1
# gemini_parser.py
#
# 负责：
# 1. 调用 Gemini
# 2. 解析雇主自然语言需求
# 3. 标准化招聘条件
# 4. 输出：
#    hard_requirements
#    preferred_requirements
# ============================================================

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from config import (
    ALLOWED_REQUIREMENT_FIELDS,
    BOOLEAN_FIELDS,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    MULTI_SELECT_FIELDS,
    STANDARD_OPTIONS,
    WORKING_CITY_OPTIONS,
)


# ============================================================
# 1. Gemini Client
# ============================================================

if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )
else:
    gemini_client = None


# ============================================================
# 2. Nationality Aliases
# ============================================================

NATIONALITY_ALIASES = {
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "british": "United Kingdom",
    "britain": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "english nationality": "United Kingdom",

    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "american": "United States",
    "america": "United States",

    "canadian": "Canada",
    "australian": "Australia",
    "new zealander": "New Zealand",
    "irish": "Ireland",
    "south african": "South Africa",
    "chinese": "China",
    "french": "France",
    "german": "Germany",
    "spanish": "Spain",
    "italian": "Italy",
}


# ============================================================
# 3. Country Aliases
# ============================================================

COUNTRY_ALIASES = {
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",

    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "america": "United States",

    "mainland china": "China",
    "mainland": "China",
    "prc": "China",
    "中国大陆": "China",
    "中国": "China",

    "hk": "Hong Kong",
    "hong kong sar": "Hong Kong",
    "香港": "Hong Kong",

    "macao": "Macau",
    "澳门": "Macau",

    "south korea": "South Korea",
    "korea": "South Korea",
}


# ============================================================
# 4. Degree Aliases
# ============================================================

DEGREE_ALIASES = {
    "high school diploma": "High School",
    "secondary school": "High School",

    "associate": "Associate Degree",
    "associate degree": "Associate Degree",
    "associate's degree": "Associate Degree",
    "associates degree": "Associate Degree",

    "bachelor": "Bachelor",
    "bachelor degree": "Bachelor",
    "bachelor's degree": "Bachelor",
    "undergraduate degree": "Bachelor",
    "undergraduate": "Bachelor",
    "ba": "Bachelor",
    "b.a.": "Bachelor",
    "bsc": "Bachelor",
    "b.sc.": "Bachelor",

    "master": "Master",
    "master degree": "Master",
    "master's degree": "Master",
    "masters degree": "Master",
    "postgraduate degree": "Master",
    "ma": "Master",
    "m.a.": "Master",
    "msc": "Master",
    "m.sc.": "Master",

    "doctorate": "Doctorate",
    "doctoral degree": "Doctorate",
    "phd": "Doctorate",
    "ph.d.": "Doctorate",
}


# ============================================================
# 5. Subject Aliases
# ============================================================

SUBJECT_ALIASES = {
    "math": "Mathematics",
    "maths": "Mathematics",
    "数学": "Mathematics",

    "english language": "English",
    "英语": "English",

    "general science": "Science",
    "science": "Science",
    "科学": "Science",

    "bio": "Biology",
    "生物": "Biology",

    "chem": "Chemistry",
    "化学": "Chemistry",

    "physics": "Physics",
    "物理": "Physics",

    "history": "History",
    "历史": "History",

    "geography": "Geography",
    "地理": "Geography",

    "economics": "Economics",
    "经济": "Economics",
    "经济学": "Economics",

    "business studies": "Business",
    "business": "Business",
    "商科": "Business",

    "computing": "Computer Science",
    "computer": "Computer Science",
    "information technology": "Computer Science",
    "it": "Computer Science",
    "计算机": "Computer Science",

    "physical education": "PE / Sports",
    "sports": "PE / Sports",
    "sport": "PE / Sports",
    "pe": "PE / Sports",
    "体育": "PE / Sports",

    "foreign languages": "Languages",
    "modern languages": "Languages",
    "languages": "Languages",
    "语言": "Languages",

    "early childhood": "Early Years",
    "early years education": "Early Years",
    "preschool": "Early Years",
    "early learning": "Early Years",
    "早教": "Early Years",
    "幼儿教育": "Early Years",

    "primary": "Primary Education",
    "primary education": "Primary Education",
    "elementary education": "Primary Education",
    "小学教育": "Primary Education",

    "special needs": "Special Education",
    "sen": "Special Education",
    "special education": "Special Education",
    "特殊教育": "Special Education",
}


# ============================================================
# 6. Curriculum Aliases
# ============================================================

CURRICULUM_ALIASES = {
    "international baccalaureate": "IB",
    "ib curriculum": "IB",
    "ib programme": "IB",

    "international gcse": "IGCSE",
    "i-gcse": "IGCSE",

    "a level": "A-Level",
    "a levels": "A-Level",
    "a-levels": "A-Level",

    "advanced placement": "AP",

    "early years foundation stage": "EYFS",

    "reggio": "Reggio Emilia",
    "reggio emilia approach": "Reggio Emilia",

    "cambridge curriculum": "Cambridge",
    "cambridge international": "Cambridge",

    "american": "American Curriculum",
    "american curriculum": "American Curriculum",
    "us curriculum": "American Curriculum",
    "american system": "American Curriculum",

    "national curriculum": "Local Curriculum",
    "local school curriculum": "Local Curriculum",
}


# ============================================================
# 7. Language Aliases
# ============================================================

LANGUAGE_ALIASES = {
    "chinese": "Mandarin",
    "mandarin chinese": "Mandarin",
    "putonghua": "Mandarin",
    "普通话": "Mandarin",
    "中文": "Mandarin",

    "cantonese chinese": "Cantonese",
    "粤语": "Cantonese",

    "english language": "English",
    "英语": "English",

    "french language": "French",
    "法语": "French",

    "german language": "German",
    "德语": "German",

    "spanish language": "Spanish",
    "西班牙语": "Spanish",

    "italian language": "Italian",
    "意大利语": "Italian",

    "japanese language": "Japanese",
    "日语": "Japanese",

    "korean language": "Korean",
    "韩语": "Korean",
}


# ============================================================
# 8. City Aliases
# ============================================================

CITY_ALIASES = {
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

    "香港": "Hong Kong",
    "香港特别行政区": "Hong Kong",
    "hk": "Hong Kong",
    "hong kong sar": "Hong Kong",

    "澳门": "Macau",
    "澳门特别行政区": "Macau",
    "macao": "Macau",

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

    "任何城市": "Any City",
    "任意城市": "Any City",
    "全国": "Any City",
    "全国均可": "Any City",
    "不限城市": "Any City",

    "anywhere": "Any City",
    "any location": "Any City",
    "any city": "Any City",
}


# ============================================================
# 9. General Text Normalization
# ============================================================

def normalize_text(
    value: Any
) -> str:
    """
    文本统一：
    - 去除前后空格
    - 转小写
    - 标准化破折号
    - 合并连续空格
    """

    if value is None:
        return ""

    text = str(
        value
    ).strip().lower()

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
        text
    )

    return text


# ============================================================
# 10. Ensure List
# ============================================================

def ensure_list(
    value: Any
) -> List[Any]:
    """
    将单值统一转换成列表。
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


# ============================================================
# 11. Standard Option Lookup
# ============================================================

def find_standard_option(
    field: str,
    value: Any,
) -> Optional[str]:
    """
    在 STANDARD_OPTIONS 中做
    不区分大小写的精确匹配。
    """

    normalized_value = (
        normalize_text(
            value
        )
    )

    for option in (
        STANDARD_OPTIONS.get(
            field,
            []
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
# 12. Number Parsing
# ============================================================

def normalize_number(
    value: Any
) -> Optional[float]:
    """
    将数字表达转换成 float。

    支持：

    20个月
    -> 1.67

    18个月
    -> 1.5

    一岁半
    -> 1.5

    10岁
    -> 10

    5 years
    -> 5
    """

    if value is None:
        return None

    if isinstance(
        value,
        (
            int,
            float,
        )
    ):
        return float(
            value
        )

    text = str(
        value
    ).strip()

    # --------------------------------------------------------
    # 几个月
    # --------------------------------------------------------

    month_match = re.search(
        r"(\d+(?:\.\d+)?)\s*个月",
        text
    )

    if month_match:
        months = float(
            month_match.group(1)
        )

        return round(
            months / 12,
            2
        )

    # --------------------------------------------------------
    # 中文常用年龄
    # --------------------------------------------------------

    chinese_age_map = {
        "半岁": 0.5,
        "一岁": 1.0,
        "一岁半": 1.5,
        "两岁": 2.0,
        "两岁半": 2.5,
        "三岁": 3.0,
        "三岁半": 3.5,
        "四岁": 4.0,
        "四岁半": 4.5,
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
    ) in chinese_age_map.items():
        if expression in text:
            return number

    # --------------------------------------------------------
    # 普通数字
    # --------------------------------------------------------

    number_match = re.search(
        r"\d+(?:\.\d+)?",
        text
    )

    if not number_match:
        return None

    return float(
        number_match.group(0)
    )


# ============================================================
# 13. Boolean Parsing
# ============================================================

def normalize_boolean(
    value: Any
) -> Optional[bool]:
    """
    将常见 yes / no 表达
    标准化成 True / False。
    """

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
# 14. Single Option Normalization
# ============================================================

def normalize_single_option(
    field: str,
    value: Any,
) -> Optional[str]:
    """
    标准化单值字段。
    """

    if value is None:
        return None

    direct_match = (
        find_standard_option(
            field,
            value
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
                str(value).strip()
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

        direct_city = (
            find_standard_option(
                "Working City",
                value
            )
        )

        if direct_city:
            return direct_city

        # 未知城市可以保留，
        # 但后续 matcher 很可能无法匹配
        return str(
            value
        ).strip()

    # --------------------------------------------------------
    # Visa Status
    # --------------------------------------------------------

    if (
        field
        ==
        "Visa Status"
    ):
        return str(
            value
        ).strip()

    return None


# ============================================================
# 15. Multiple Option Normalization
# ============================================================

def normalize_multi_option(
    field: str,
    value: Any,
) -> Optional[str]:
    """
    标准化多选字段中的一个值。
    """

    if value is None:
        return None

    direct_match = (
        find_standard_option(
            field,
            value
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
    # Visa Countries
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
            return country_value

        direct_country = (
            find_standard_option(
                field,
                value
            )
        )

        if direct_country:
            return direct_country

    return None


# ============================================================
# 16. Requirement Field Normalization
# ============================================================

def normalize_requirement_field(
    field: str,
    value: Any,
) -> Tuple[
    Any,
    List[str]
]:
    """
    标准化一项招聘条件。

    返回：
    normalized_value
    warnings
    """

    warnings = []

    # --------------------------------------------------------
    # Ignore unsupported fields
    # --------------------------------------------------------

    if (
        field
        not in
        ALLOWED_REQUIREMENT_FIELDS
    ):
        warnings.append(
            f"忽略未参与匹配字段："
            f"{field}"
        )

        return (
            None,
            warnings
        )

    # --------------------------------------------------------
    # Number fields
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
                f"{field}：{value}"
            )

        return (
            normalized_value,
            warnings
        )

    # --------------------------------------------------------
    # Boolean
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
                f"无法识别布尔字段 "
                f"{field}：{value}"
            )

        return (
            normalized_value,
            warnings
        )

    # --------------------------------------------------------
    # Multiple select
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
                    raw_value
                )
            )

            if (
                normalized_item
                is None
            ):
                warnings.append(
                    f"无法标准化 "
                    f"{field}："
                    f"{raw_value}"
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
                warnings
            )

        return (
            normalized_values,
            warnings
        )

    # --------------------------------------------------------
    # Single select / text
    # --------------------------------------------------------

    normalized_value = (
        normalize_single_option(
            field,
            value
        )
    )

    if (
        normalized_value
        is None
    ):
        warnings.append(
            f"无法标准化 "
            f"{field}："
            f"{value}"
        )

    return (
        normalized_value,
        warnings
    )


# ============================================================
# 17. Requirement Group Normalization
# ============================================================

def normalize_requirement_group(
    requirements: Dict[
        str,
        Any
    ]
) -> Tuple[
    Dict[str, Any],
    List[str]
]:
    """
    标准化：
    hard_requirements
    或
    preferred_requirements
    """

    normalized_requirements = {}

    warnings = []

    if not isinstance(
        requirements,
        dict
    ):
        return (
            {},
            [
                "Requirements 格式错误，"
                "不是 dictionary。"
            ]
        )

    for (
        field,
        value
    ) in requirements.items():

        if value is None:
            continue

        if value == "":
            continue

        if value == []:
            continue

        (
            normalized_value,
            field_warnings
        ) = (
            normalize_requirement_field(
                field,
                value
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
        warnings
    )


# ============================================================
# 18. Gemini JSON Cleanup
# ============================================================

def clean_gemini_json(
    text: str
) -> str:
    """
    清理 Gemini 偶尔返回的 Markdown。
    """

    cleaned_text = (
        text.strip()
    )

    cleaned_text = (
        cleaned_text.replace(
            "```json",
            ""
        )
    )

    cleaned_text = (
        cleaned_text.replace(
            "```JSON",
            ""
        )
    )

    cleaned_text = (
        cleaned_text.replace(
            "```",
            ""
        )
    )

    cleaned_text = (
        cleaned_text.strip()
    )

    json_match = re.search(
        r"\{.*\}",
        cleaned_text,
        re.DOTALL
    )

    if json_match:
        return (
            json_match.group(0)
        )

    return cleaned_text


# ============================================================
# 19. Gemini Prompt
# ============================================================

def build_requirement_prompt(
    employer_request: str
) -> str:
    """
    生成 Gemini 招聘需求解析 Prompt。
    """

    city_options_json = json.dumps(
        WORKING_CITY_OPTIONS,
        ensure_ascii=False,
        indent=2
    )

    standard_options_json = (
        json.dumps(
            STANDARD_OPTIONS,
            ensure_ascii=False,
            indent=2
        )
    )

    prompt = f"""
You are the requirement parser for an international
teacher, private educator and family education recruitment
system.

Your job is to convert an employer's natural-language request
into structured matching requirements.

Return ONLY valid JSON.

The JSON MUST use this exact top-level structure:

{{
  "hard_requirements": {{}},
  "preferred_requirements": {{}}
}}

Allowed matching fields:

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

IMPORTANT RULES:

1. NEVER output "Current City".

The employer's family location or job location is NOT the
teacher's current city.

Use:

"Working City"

Example:

北京家庭
→
"Working City": "Beijing"

杭州工作
→
"Working City": "Hangzhou"

上海家庭
→
"Working City": "Shanghai"


2. NEVER output "Desired Position".

Do NOT use these job titles as matching requirements:

Governor
Governess
Private Tutor
Tutor
Nanny Educator
Teacher
Homeschool Teacher
Subject Specialist

Job title information should be ignored for matching.


3. CHILD AGE

If the employer mentions the child's age, output:

"Child Age": number

Examples:

20个月
→
"Child Age": 1.67

18个月
→
"Child Age": 1.5

一岁半
→
"Child Age": 1.5

2岁
→
"Child Age": 2

10岁
→
"Child Age": 10

Do NOT output Age Groups.


4. WORKING CITY

Use one of these standard city values whenever possible:

{city_options_json}


5. MULTIPLE VALUE FIELDS

The following fields MUST always be JSON arrays:

Subjects
Curriculum
Teaching Languages
Visa / Work Authorization Countries


6. BOOLEAN FIELDS

Use true or false for:

SEN Experience
International School Experience
Private Tutoring Experience
Live-in
Willing to Travel
Driving
Nanny Educator Experience


7. HARD REQUIREMENTS

Words such as:

must
required
essential
mandatory
必须
要求
一定要
需要

normally mean the field belongs in:

hard_requirements


8. PREFERRED REQUIREMENTS

Words such as:

preferred
preferably
ideally
nice to have
最好
优先
希望
有...更好

normally mean the field belongs in:

preferred_requirements


9. DO NOT INVENT REQUIREMENTS

Only include requirements explicitly stated or clearly implied
by the employer.

Do not assume nationality.
Do not assume visa.
Do not assume driving.
Do not assume live-in.
Do not assume curriculum.
Do not assume degree.


10. STANDARD DATABASE VALUES

Use these standard values whenever possible:

{standard_options_json}


EMPLOYER REQUEST:

{employer_request}
"""

    return prompt


# ============================================================
# 20. Parse Employer Requirement
# ============================================================

def parse_employer_requirement(
    employer_request: str
) -> Dict[str, Any]:
    """
    核心函数：

    雇主自然语言
    ↓
    Gemini
    ↓
    JSON
    ↓
    标准化
    """

    if not employer_request:
        raise ValueError(
            "Employer request 不能为空。"
        )

    if gemini_client is None:
        raise RuntimeError(
            "Gemini API Key 未配置。"
        )

    if not GEMINI_MODEL:
        raise RuntimeError(
            "Gemini Model 未配置。"
        )

    prompt = (
        build_requirement_prompt(
            employer_request
        )
    )

    response = (
        gemini_client
        .models
        .generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
    response_mime_type="application/json",
)
            )
        )
    )

    response_text = (
        response.text
    )

    if not response_text:
        raise RuntimeError(
            "Gemini 没有返回内容。"
        )

    cleaned_text = (
        clean_gemini_json(
            response_text
        )
    )

    try:
        raw_requirements = (
            json.loads(
                cleaned_text
            )
        )

    except (
        json.JSONDecodeError
    ) as error:

        raise ValueError(
            "Gemini 返回内容不是有效 JSON。\n"
            f"原始内容："
            f"{response_text}"
        ) from error

    hard_raw = (
        raw_requirements.get(
            "hard_requirements",
            {}
        )
    )

    preferred_raw = (
        raw_requirements.get(
            "preferred_requirements",
            {}
        )
    )

    (
        hard_requirements,
        hard_warnings
    ) = (
        normalize_requirement_group(
            hard_raw
        )
    )

    (
        preferred_requirements,
        preferred_warnings
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
            employer_request
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
# 21. Gemini Health Check
# ============================================================

def check_gemini_connection() -> Dict[str, Any]:
    """
    测试 Gemini 是否正常。
    """

    if gemini_client is None:
        return {
            "success": False,
            "message": (
                "Gemini API Key 未配置"
            ),
        }

    if not GEMINI_MODEL:
        return {
            "success": False,
            "message": (
                "Gemini Model 未配置"
            ),
        }

    try:
        response = (
            gemini_client
            .models
            .generate_content(
                model=GEMINI_MODEL,
                contents=(
                    "Reply only with: OK"
                ),
            )
        )

        if response.text:
            return {
                "success": True,
                "message": (
                    "Gemini 连接正常"
                ),
            }

        return {
            "success": False,
            "message": (
                "Gemini 没有返回内容"
            ),
        }

    except Exception as error:
        return {
            "success": False,
            "message": str(
                error
            ),
        }
