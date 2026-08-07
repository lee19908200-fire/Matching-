# ============================================================
# Teacher Matching System V1.1
# gemini_parser.py
# ============================================================

import json
import re

from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

import config


# ============================================================
# 1. Config
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
# 2. Client
# ============================================================

if GEMINI_API_KEY:

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

else:

    gemini_client = None


_ACTIVE_MODEL = None


# ============================================================
# 3. Aliases
# ============================================================

CITY_ALIASES = {

    "北京": "Beijing",
    "北京市": "Beijing",

    "上海": "Shanghai",
    "上海市": "Shanghai",

    "深圳": "Shenzhen",
    "深圳市": "Shenzhen",

    "广州": "Guangzhou",
    "广州市": "Guangzhou",

    "成都": "Chengdu",
    "杭州": "Hangzhou",
    "重庆": "Chongqing",
    "武汉": "Wuhan",
    "南京": "Nanjing",
    "苏州": "Suzhou",

    "西安": "Xi'an",
    "xian": "Xi'an",

    "天津": "Tianjin",
    "长沙": "Changsha",
    "郑州": "Zhengzhou",
    "东莞": "Dongguan",
    "宁波": "Ningbo",
    "佛山": "Foshan",
    "合肥": "Hefei",
    "青岛": "Qingdao",
    "昆明": "Kunming",
    "沈阳": "Shenyang",
    "济南": "Jinan",
    "厦门": "Xiamen",
    "福州": "Fuzhou",
    "大连": "Dalian",
    "哈尔滨": "Harbin",
    "长春": "Changchun",
    "石家庄": "Shijiazhuang",
    "南昌": "Nanchang",
    "南宁": "Nanning",
    "贵阳": "Guiyang",
    "太原": "Taiyuan",
    "无锡": "Wuxi",
    "温州": "Wenzhou",
    "珠海": "Zhuhai",
    "三亚": "Sanya",
    "海口": "Haikou",

    "香港": "Hong Kong",
    "澳门": "Macau",

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
    "不限城市": "Any City",
}


DEGREE_ALIASES = {

    "high school": "High School",
    "高中": "High School",

    "diploma": "Diploma",

    "associate": "Associate Degree",
    "associate degree": "Associate Degree",

    "bachelor": "Bachelor",
    "bachelor's degree": "Bachelor",
    "本科": "Bachelor",
    "学士": "Bachelor",

    "master": "Master",
    "master's degree": "Master",
    "硕士": "Master",

    "doctorate": "Doctorate",
    "phd": "Doctorate",
    "博士": "Doctorate",
}


SUBJECT_ALIASES = {

    "english": "English",
    "英语": "English",

    "math": "Mathematics",
    "maths": "Mathematics",
    "数学": "Mathematics",

    "science": "Science",
    "科学": "Science",

    "physics": "Physics",
    "物理": "Physics",

    "chemistry": "Chemistry",
    "化学": "Chemistry",

    "biology": "Biology",
    "生物": "Biology",

    "history": "History",
    "历史": "History",

    "geography": "Geography",
    "地理": "Geography",

    "early years": "Early Years",
    "early childhood": "Early Years",
    "早教": "Early Years",
    "幼教": "Early Years",
    "幼儿教育": "Early Years",

    "primary": "Primary Education",
    "primary education": "Primary Education",
    "小学教育": "Primary Education",

    "sen": "Special Education",
    "special education": "Special Education",
    "特殊教育": "Special Education",
}


LANGUAGE_ALIASES = {

    "english": "English",
    "英语": "English",

    "mandarin": "Mandarin",
    "chinese": "Mandarin",
    "中文": "Mandarin",
    "普通话": "Mandarin",

    "cantonese": "Cantonese",
    "粤语": "Cantonese",

    "french": "French",
    "法语": "French",

    "german": "German",
    "德语": "German",

    "spanish": "Spanish",
    "西班牙语": "Spanish",
}


# ============================================================
# 4. Generic Helpers
# ============================================================

def normalize_text(
    value: Any
) -> str:

    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .lower()
    )


def ensure_list(
    value: Any
) -> List[Any]:

    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def normalize_model_name(
    value: Any
) -> str:

    if not value:
        return ""

    name = str(value).strip()

    if name.startswith(
        "models/"
    ):

        name = name[
            len("models/"):
        ]

    return name


# ============================================================
# 5. Models
# ============================================================

def list_generate_content_models():

    if gemini_client is None:
        return []

    result = []

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
                actions
                and
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

            if name:
                result.append(name)

    except Exception:
        return []

    return result


def resolve_gemini_model(
    force_refresh: bool = False
):

    global _ACTIVE_MODEL

    if (
        _ACTIVE_MODEL
        and not force_refresh
    ):
        return _ACTIVE_MODEL

    configured = (
        normalize_model_name(
            GEMINI_MODEL
        )
    )

    available = (
        list_generate_content_models()
    )

    if available:

        if (
            configured
            and configured in available
        ):

            _ACTIVE_MODEL = configured

            return _ACTIVE_MODEL

        for model in available:

            if "flash" in model.lower():

                _ACTIVE_MODEL = model

                return _ACTIVE_MODEL

        _ACTIVE_MODEL = available[0]

        return _ACTIVE_MODEL

    if configured:

        _ACTIVE_MODEL = configured

        return _ACTIVE_MODEL

    raise RuntimeError(
        "没有找到可用 Gemini 模型。"
    )


# ============================================================
# 6. Number Parsing
# ============================================================

def normalize_number(
    value: Any
) -> Optional[float]:

    if value is None:
        return None

    if isinstance(
        value,
        (int, float),
    ):

        return float(value)

    text = str(value).strip()

    month_match = re.search(
        r"(\d+(?:\.\d+)?)\s*个月",
        text,
    )

    if month_match:

        return round(
            float(
                month_match.group(1)
            )
            / 12,
            2,
        )

    chinese_map = {
        "半岁": 0.5,
        "一岁": 1,
        "一岁半": 1.5,
        "两岁": 2,
        "两岁半": 2.5,
        "三岁": 3,
        "四岁": 4,
        "五岁": 5,
        "六岁": 6,
        "七岁": 7,
        "八岁": 8,
        "九岁": 9,
        "十岁": 10,
    }

    for word, number in (
        chinese_map.items()
    ):

        if word in text:

            return float(number)

    match = re.search(
        r"\d+(?:\.\d+)?",
        text,
    )

    if not match:
        return None

    return float(
        match.group(0)
    )


# ============================================================
# 7. Boolean
# ============================================================

def normalize_boolean(
    value: Any
):

    if isinstance(value, bool):
        return value

    text = normalize_text(value)

    if text in {
        "true",
        "yes",
        "1",
        "是",
        "需要",
        "必须",
        "愿意",
        "有",
    }:

        return True

    if text in {
        "false",
        "no",
        "0",
        "否",
        "不",
        "没有",
    }:

        return False

    return None


# ============================================================
# 8. Normalize Fields
# ============================================================

def normalize_requirement_field(
    field: str,
    value: Any,
) -> Tuple[Any, List[str]]:

    warnings = []

    if field in {
        "Child Age",
        "Minimum Years of Teaching",
        "Minimum Teacher Age",
        "Maximum Teacher Age",
    }:

        number = normalize_number(
            value
        )

        if number is None:

            warnings.append(
                f"无法识别数字：{field}"
            )

        return number, warnings

    if field == "Minimum Degree":

        key = normalize_text(
            value
        )

        if key in DEGREE_ALIASES:

            return (
                DEGREE_ALIASES[key],
                warnings,
            )

        for option in (
            STANDARD_OPTIONS.get(
                "Minimum Degree",
                []
            )
        ):

            if (
                normalize_text(option)
                ==
                key
            ):

                return option, warnings

        warnings.append(
            f"无法识别学历：{value}"
        )

        return None, warnings

    if field == "Working City":

        key = normalize_text(
            value
        )

        if key in CITY_ALIASES:

            return (
                CITY_ALIASES[key],
                warnings,
            )

        for city in WORKING_CITY_OPTIONS:

            if (
                normalize_text(city)
                ==
                key
            ):

                return city, warnings

        return (
            str(value).strip(),
            warnings,
        )

    if field == "Private Room Provided":

        result = normalize_boolean(
            value
        )

        return result, warnings

    if field in BOOLEAN_FIELDS:

        result = normalize_boolean(
            value
        )

        return result, warnings

    if field in MULTI_SELECT_FIELDS:

        result = []

        for item in ensure_list(value):

            key = normalize_text(
                item
            )

            normalized = None

            if field == "Subjects":

                normalized = (
                    SUBJECT_ALIASES.get(
                        key
                    )
                )

            elif field == "Teaching Languages":

                normalized = (
                    LANGUAGE_ALIASES.get(
                        key
                    )
                )

            if normalized is None:

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
                        key
                    ):

                        normalized = option

                        break

            if normalized is not None:

                if normalized not in result:

                    result.append(
                        normalized
                    )

        if not result:

            warnings.append(
                f"无法标准化：{field}"
            )

            return None, warnings

        return result, warnings

    # Text
    return (
        str(value).strip(),
        warnings,
    )


# ============================================================
# 9. Normalize Group
# ============================================================

def normalize_requirement_group(
    requirements: Dict[str, Any]
):

    result = {}

    warnings = []

    if not isinstance(
        requirements,
        dict,
    ):

        return {}, [
            "Requirement 不是 dictionary"
        ]

    for field, value in (
        requirements.items()
    ):

        if field in {
            "Current City",
            "Desired Position",
            "Age Groups",
        }:

            continue

        if (
            field
            not in
            ALLOWED_REQUIREMENT_FIELDS
        ):

            warnings.append(
                f"忽略字段：{field}"
            )

            continue

        if value in {
            None,
            "",
        }:

            continue

        normalized, field_warnings = (
            normalize_requirement_field(
                field,
                value,
            )
        )

        warnings.extend(
            field_warnings
        )

        if normalized is not None:

            result[field] = normalized

    return result, warnings


# ============================================================
# 10. Prompt
# ============================================================

def build_requirement_prompt(
    employer_request: str
):

    city_json = json.dumps(
        WORKING_CITY_OPTIONS,
        ensure_ascii=False,
    )

    return f"""
You are the requirement parser for a private teacher and
family educator recruitment system.

Return ONLY valid JSON.

Use EXACTLY this top level structure:

{{
  "hard_requirements": {{}},
  "preferred_requirements": {{}},
  "reference_requirements": {{}}
}}

Allowed fields:

Working City
Nationality
Current Country
Visa Status
Visa / Work Authorization Countries
Minimum Teacher Age
Maximum Teacher Age
Minimum Degree
Minimum Years of Teaching
Teaching Languages
Subjects
Curriculum
Live-in
Night Care
Private Room Provided
Driving
Willing to Travel
SEN Experience
International School Experience
Private Tutoring Experience
Nanny Educator Experience
Child Age

IMPORTANT RULES:

1.
Employer/family/job location -> Working City.

Never use Current City for job location.

Examples:

北京家庭
-> Working City = Beijing

杭州家庭
-> Working City = Hangzhou

Available city values:

{city_json}


2.
Teacher age and child age are DIFFERENT.

"老师40岁以内"
"40以内"
"年龄不超过40"

means:

"Maximum Teacher Age": 40

Do NOT treat this as Child Age.


3.
Child age is REFERENCE ONLY.

If the family says:

4岁孩子

put:

"Child Age": 4

inside:

reference_requirements

NOT hard_requirements.


4.
Degree:

本科以上
Bachelor or above

->

"Minimum Degree": "Bachelor"

硕士以上
->

"Minimum Degree": "Master"


5.
Private room:

老师独立房间
提供独立房间
有独立房间

->

"Private Room Provided": true


6.
Night care / sleeping:

需要带睡
需要陪睡
需要夜间照护

->

"Night Care": true


But:

不用带睡
不需要带睡
不用陪睡
不需要夜间照护

means Night Care is NOT REQUIRED.

DO NOT output:

"Night Care": false

Simply omit Night Care entirely.


7.
Live-in:

住家老师
住家教师
需要住家

->

"Live-in": true


8.
Teaching languages:

英语好
英语流利
英语母语
英文好

->

"Teaching Languages": ["English"]


9.
Job titles MUST NOT be matching fields.

Ignore:

Governor
Governess
Tutor
Teacher
Private Tutor
Nanny Educator
家庭教师
家庭老师
育儿师

Do NOT output Desired Position.


10.
Words such as:

必须
要求
需要
一定要
must
required

usually belong to hard_requirements.


11.
Words such as:

最好
优先
希望
prefer
preferred
ideally

usually belong to preferred_requirements.


12.
Do not invent requirements.


EMPLOYER REQUEST:

{employer_request}

Return JSON only.
"""


# ============================================================
# 11. Clean JSON
# ============================================================

def clean_json(
    text: str
):

    text = (
        text
        .replace(
            "```json",
            ""
        )
        .replace(
            "```",
            ""
        )
        .strip()
    )

    match = re.search(
        r"\{.*\}",
        text,
        re.DOTALL,
    )

    if match:
        return match.group(0)

    return text


# ============================================================
# 12. Parse Employer Requirement
# ============================================================

def parse_employer_requirement(
    employer_request: str
):

    if gemini_client is None:

        raise RuntimeError(
            "Gemini API Key 未配置。"
        )

    request_text = (
        str(
            employer_request
        )
        .strip()
    )

    if not request_text:

        raise ValueError(
            "雇主需求不能为空。"
        )

    model_name = (
        resolve_gemini_model()
    )

    response = (
        gemini_client
        .models
        .generate_content(
            model=model_name,
            contents=(
                build_requirement_prompt(
                    request_text
                )
            ),
            config=(
                types.GenerateContentConfig(
                    response_mime_type=(
                        "application/json"
                    )
                )
            ),
        )
    )

    if not response.text:

        raise RuntimeError(
            "Gemini 没有返回内容。"
        )

    raw = json.loads(
        clean_json(
            response.text
        )
    )

    hard_raw = raw.get(
        "hard_requirements",
        {},
    )

    preferred_raw = raw.get(
        "preferred_requirements",
        {},
    )

    reference_raw = raw.get(
        "reference_requirements",
        {},
    )

    hard, hard_warnings = (
        normalize_requirement_group(
            hard_raw
        )
    )

    preferred, preferred_warnings = (
        normalize_requirement_group(
            preferred_raw
        )
    )

    reference, reference_warnings = (
        normalize_requirement_group(
            reference_raw
        )
    )

    # Child Age 必须归到 Reference
    if "Child Age" in hard:

        reference[
            "Child Age"
        ] = hard.pop(
            "Child Age"
        )

    if "Child Age" in preferred:

        reference[
            "Child Age"
        ] = preferred.pop(
            "Child Age"
        )

    return {
        "original_request": request_text,
        "model_used": model_name,
        "raw_requirements": raw,
        "hard_requirements": hard,
        "preferred_requirements": preferred,
        "reference_requirements": reference,
        "warnings": (
            hard_warnings
            + preferred_warnings
            + reference_warnings
        ),
    }


# ============================================================
# 13. Health Check
# ============================================================

def check_gemini_connection():

    if gemini_client is None:

        return {
            "success": False,
            "message": (
                "Gemini API Key 未配置"
            ),
            "model": None,
        }

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
                contents="Reply only OK",
            )
        )

        if response.text:

            return {
                "success": True,
                "message": (
                    "Gemini 已连接"
                ),
                "model": model_name,
            }

        return {
            "success": False,
            "message": (
                "Gemini 没有返回文本"
            ),
            "model": model_name,
        }

    except Exception as error:

        return {
            "success": False,
            "message": str(error),
            "model": None,
        }
