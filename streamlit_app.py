# ============================================================
# AI Teacher Matching System V1.7
# Single-file Streamlit app
#
# Goals
# - Support single-order, AI-normalized mixed-platform batch orders, and teacher-to-orders matching
# - Normalize mixed-platform employer text to a canonical editable order format before matching
# - Read teachers from Baserow and rank them against one or many confirmed standard orders
# - Match only job-relevant qualifications / work conditions
# - Keep candidate age, gender, nationality/hometown and appearance
#   requirements in a manual-review section; they do NOT affect
#   automatic ranking or eligibility.
# - Treat missing teacher data as "待确认", not as automatic failure.
# - Unknown hard conditions reduce the displayed match score, so pending candidates cannot show misleading 100%.
# - Child age is a reference-fit signal only, not a hard rejection.
# ============================================================

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import streamlit as st
from google import genai
from google.genai import types


# ============================================================
# 1. PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Teacher Matching System V1.7",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {max-width: 1500px; padding-top: 1.7rem; padding-bottom: 3rem;}
      .main-title {font-size: 42px; font-weight: 760; margin-bottom: 4px;}
      .main-subtitle {color: #777; font-size: 16px; margin-bottom: 28px;}
      .section-title {font-size: 25px; font-weight: 720; margin-top: 12px; margin-bottom: 12px;}
      .muted {color:#777; font-size: 13px;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 2. SECRETS / CONFIG
# ============================================================


def get_secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        return default


BASEROW_TOKEN = get_secret("BASEROW_TOKEN")
TABLE_ID_RAW = get_secret("TABLE_ID")
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
GEMINI_MODEL = str(get_secret("GEMINI_MODEL", "gemini-3.6-flash") or "gemini-3.6-flash").strip()

try:
    TABLE_ID = int(TABLE_ID_RAW) if TABLE_ID_RAW is not None else None
except (TypeError, ValueError):
    TABLE_ID = None

BASEROW_BASE_URL = "https://api.baserow.io"
BASEROW_PAGE_SIZE = 200
REQUEST_TIMEOUT = 30
TOP_N = 10
BATCH_CHUNK_SIZE = 5

HARD_WEIGHT = 0.70
PREFERRED_WEIGHT = 0.20
REFERENCE_WEIGHT = 0.10

DEGREE_RANK = {
    "High School": 1,
    "Diploma": 2,
    "Associate Degree": 3,
    "Bachelor": 4,
    "Master": 5,
    "Doctorate": 6,
}

CITY_ALIASES = {
    "北京": "Beijing", "北京市": "Beijing",
    "上海": "Shanghai", "上海市": "Shanghai",
    "深圳": "Shenzhen", "深圳市": "Shenzhen",
    "广州": "Guangzhou", "广州市": "Guangzhou",
    "成都": "Chengdu", "成都市": "Chengdu",
    "杭州": "Hangzhou", "杭州市": "Hangzhou",
    "重庆": "Chongqing", "重庆市": "Chongqing",
    "武汉": "Wuhan", "武汉市": "Wuhan",
    "南京": "Nanjing", "南京市": "Nanjing",
    "苏州": "Suzhou", "苏州市": "Suzhou",
    "西安": "Xi'an", "西安市": "Xi'an", "xian": "Xi'an", "xi an": "Xi'an",
    "天津": "Tianjin", "天津市": "Tianjin",
    "长沙": "Changsha", "长沙市": "Changsha",
    "郑州": "Zhengzhou", "郑州市": "Zhengzhou",
    "东莞": "Dongguan", "东莞市": "Dongguan",
    "宁波": "Ningbo", "宁波市": "Ningbo",
    "佛山": "Foshan", "佛山市": "Foshan",
    "合肥": "Hefei", "合肥市": "Hefei",
    "青岛": "Qingdao", "青岛市": "Qingdao",
    "昆明": "Kunming", "昆明市": "Kunming",
    "沈阳": "Shenyang", "沈阳市": "Shenyang",
    "济南": "Jinan", "济南市": "Jinan",
    "厦门": "Xiamen", "厦门市": "Xiamen",
    "福州": "Fuzhou", "福州市": "Fuzhou",
    "大连": "Dalian", "大连市": "Dalian",
    "哈尔滨": "Harbin", "哈尔滨市": "Harbin",
    "长春": "Changchun", "长春市": "Changchun",
    "石家庄": "Shijiazhuang", "石家庄市": "Shijiazhuang",
    "南昌": "Nanchang", "南昌市": "Nanchang",
    "南宁": "Nanning", "南宁市": "Nanning",
    "贵阳": "Guiyang", "贵阳市": "Guiyang",
    "太原": "Taiyuan", "太原市": "Taiyuan",
    "无锡": "Wuxi", "无锡市": "Wuxi",
    "温州": "Wenzhou", "温州市": "Wenzhou",
    "珠海": "Zhuhai", "珠海市": "Zhuhai",
    "三亚": "Sanya", "三亚市": "Sanya",
    "海口": "Haikou", "海口市": "Haikou",
    "宜昌": "Yichang", "宜昌市": "Yichang",
    "沧州": "Cangzhou", "沧州市": "Cangzhou",
    "上饶": "Shangrao", "上饶市": "Shangrao",
    "南通": "Nantong", "南通市": "Nantong",
    "香港": "Hong Kong", "澳门": "Macau",
    "新加坡": "Singapore", "伦敦": "London", "悉尼": "Sydney",
    "墨尔本": "Melbourne", "多伦多": "Toronto", "温哥华": "Vancouver",
    "纽约": "New York", "洛杉矶": "Los Angeles", "迪拜": "Dubai",
    "巴黎": "Paris", "东京": "Tokyo", "首尔": "Seoul",
    "任何城市": "Any City", "任意城市": "Any City", "不限城市": "Any City",
    "全国": "Any City", "全国均可": "Any City",
}

DEGREE_ALIASES = {
    "高中": "High School", "high school": "High School",
    "中专": "Diploma", "大专": "Associate Degree", "专科": "Associate Degree",
    "associate": "Associate Degree", "associate degree": "Associate Degree",
    "本科": "Bachelor", "学士": "Bachelor", "bachelor": "Bachelor", "bachelor's degree": "Bachelor",
    "研究生": "Master", "硕士": "Master", "master": "Master", "master's degree": "Master",
    "博士": "Doctorate", "phd": "Doctorate", "doctorate": "Doctorate",
}

# Requirement fields that are job-related and may be used for automated matching.
ALLOWED_MATCH_FIELDS = {
    "Working Cities",
    "Live-in Required",
    "Night Care Required",
    "Private Room Provided",
    "Driving Required",
    "Teaching Languages",
    "Minimum Degree",
    "Minimum Years of Relevant Experience",
    "Subjects",
    "Curriculum",
    "Early Years Experience",
    "Montessori Experience",
    "International School Experience",
    "Kindergarten Experience",
    "High-end Family Experience",
    "Private Tutoring Experience",
    "Nanny Educator Experience",
    "SEN / ADHD Experience",
    "Willing to Travel",
    "Cooking Required",
    "Baby Food Required",
    "Housekeeping Required",
    "School Pick-up Required",
    "Family-School Communication Required",
    "General Tutoring Experience",
    "Child Psychology Experience",
    "Luxury Hotel Experience",
    "Nutrition Planning",
    "Required Certificates",
    "Exam Preparation",
}

REFERENCE_FIELDS = {"Child Ages"}

# Candidate age, gender, nationality/hometown, appearance, etc. are deliberately
# excluded from automatic employment ranking. Gemini can preserve them under
# manual_review so a human recruiter can see the original employer request.
MANUAL_REVIEW_KEYS = {
    "Candidate Age Requirement",
    "Candidate Gender Preference",
    "Nationality / Hometown / Regional Preference",
    "Appearance / Height / Weight Preference",
    "Personality / Style Preference",
    "Education Institution / Major Preference",
    "Other Manual Review Notes",
}


# ============================================================
# 3. GENERIC HELPERS
# ============================================================


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def dedupe(values: Iterable[Any]) -> List[Any]:
    result: List[Any] = []
    seen = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def to_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    month_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:个月|months?)", text, re.IGNORECASE)
    if month_match:
        return round(float(month_match.group(1)) / 12.0, 2)
    number_match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(number_match.group(0)) if number_match else None


def boolish(value: Any) -> Optional[bool]:
    """Return True / False / None(unknown). Supports booleans and Yes/No/Unknown selects."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return boolish(value.get("value"))
    text = normalize_text(value)
    if text in {"yes", "y", "true", "1", "是", "可以", "可", "接受", "愿意", "有", "需要"}:
        return True
    if text in {"no", "n", "false", "0", "否", "不可以", "不可", "不接受", "不愿意", "没有"}:
        return False
    if text in {"unknown", "待确认", "未确认", "不确定", "未知", "n/a", "na"}:
        return None
    return None


def format_number(value: Any) -> str:
    number = to_number(value)
    if number is None:
        return "未填写"
    return str(int(number)) if number.is_integer() else str(round(number, 2))


def format_list(value: Any) -> str:
    values = ensure_list(value)
    values = [v for v in values if v not in (None, "")]
    return ", ".join(str(v) for v in values) if values else "未填写"


def tri_text(value: Any) -> str:
    state = boolish(value)
    if state is True:
        return "是"
    if state is False:
        return "否"
    return "待确认"


def normalize_city(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    raw = str(value).strip()
    key = normalize_text(raw)
    for alias, standard in CITY_ALIASES.items():
        if normalize_text(alias) == key:
            return standard
    return raw


def normalize_degree(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    key = normalize_text(value)
    for alias, standard in DEGREE_ALIASES.items():
        if normalize_text(alias) == key:
            return standard
    for degree in DEGREE_RANK:
        if normalize_text(degree) == key:
            return degree
    return str(value).strip()


def normalize_multi_text(value: Any) -> List[str]:
    result = []
    for item in ensure_list(value):
        if item is None or item == "":
            continue
        if isinstance(item, dict) and "value" in item:
            item = item["value"]
        text = str(item).strip()
        if text:
            result.append(text)
    return dedupe(result)


# ============================================================
# 4. BASEROW
# ============================================================


def normalize_baserow_value(value: Any) -> Any:
    if isinstance(value, list):
        normalized = []
        for item in value:
            if isinstance(item, dict) and "value" in item:
                normalized.append(item.get("value"))
            else:
                normalized.append(item)
        return [x for x in normalized if x is not None]
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


@st.cache_data(ttl=60, show_spinner=False)
def load_teachers() -> List[Dict[str, Any]]:
    if not BASEROW_TOKEN:
        raise RuntimeError("BASEROW_TOKEN 未配置。")
    if TABLE_ID is None:
        raise RuntimeError("TABLE_ID 未配置或格式不正确。")

    url = f"{BASEROW_BASE_URL}/api/database/rows/table/{TABLE_ID}/"
    headers = {"Authorization": f"Token {BASEROW_TOKEN}"}

    teachers: List[Dict[str, Any]] = []
    page = 1
    while True:
        response = requests.get(
            url,
            headers=headers,
            params={"user_field_names": "true", "size": BASEROW_PAGE_SIZE, "page": page},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Baserow 读取失败 HTTP {response.status_code}: {response.text[:600]}")
        payload = response.json()
        for row in payload.get("results", []):
            teacher: Dict[str, Any] = {"Baserow ID": row.get("id")}
            for field, raw in row.items():
                if field in {"id", "order"}:
                    continue
                teacher[field] = normalize_baserow_value(raw)
            # Skip blank rows.
            if teacher.get("First Name") or teacher.get("Last Name") or teacher.get("Name"):
                teachers.append(teacher)
        if not payload.get("next"):
            break
        page += 1
    return teachers


def check_baserow_connection() -> Dict[str, Any]:
    if not BASEROW_TOKEN or TABLE_ID is None:
        return {"success": False, "message": "Baserow Secrets 未配置完整。"}
    try:
        url = f"{BASEROW_BASE_URL}/api/database/rows/table/{TABLE_ID}/"
        response = requests.get(
            url,
            headers={"Authorization": f"Token {BASEROW_TOKEN}"},
            params={"user_field_names": "true", "size": 1, "page": 1},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            return {"success": True, "message": "Baserow 已连接"}
        return {"success": False, "message": f"HTTP {response.status_code}: {response.text[:300]}"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


# ============================================================
# 5. GEMINI PARSER
# ============================================================


def gemini_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 未配置。")
    return genai.Client(api_key=GEMINI_API_KEY)


def check_gemini_config() -> Dict[str, Any]:
    """No generate_content call here, so page reruns do not spend generation quota."""
    if not GEMINI_API_KEY:
        return {"success": False, "message": "GEMINI_API_KEY 未配置", "model": GEMINI_MODEL}
    return {"success": True, "message": "Gemini 已配置", "model": GEMINI_MODEL}


def list_generate_models(client: genai.Client) -> List[str]:
    result = []
    try:
        for model in client.models.list():
            actions = getattr(model, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            name = str(getattr(model, "name", "") or "").strip()
            if name.startswith("models/"):
                name = name[len("models/"):]
            if name:
                result.append(name)
    except Exception:
        return []
    return dedupe(result)


def build_parser_prompt(employer_request: str) -> str:
    return f"""
You parse ONE private-family recruitment order into structured JSON.
Return JSON only. Do not include markdown.

IMPORTANT EMPLOYMENT-SAFETY RULE:
Candidate age, gender, nationality/hometown/regional exclusions, appearance, height/weight,
and personality/style preferences must NEVER be placed in hard_requirements or preferred_requirements.
Preserve them only under manual_review for a human recruiter. They must not affect automated ranking.

TOP-LEVEL JSON STRUCTURE:
{{
  "order_info": {{
    "Order ID": null,
    "Job Type": null,
    "Working Cities": [],
    "Job District": null,
    "Salary Text": null,
    "Work Schedule": null,
    "Start Date": null,
    "Live-in Job": null,
    "Child Ages": [],
    "Child Count": null,
    "Special Needs": []
  }},
  "hard_requirements": {{}},
  "preferred_requirements": {{}},
  "reference_requirements": {{}},
  "manual_review": {{}}
}}

AUTOMATED MATCHING FIELDS ALLOWED IN hard_requirements / preferred_requirements:
- Working Cities: array of standardized English city names
- Live-in Required: boolean
- Night Care Required: boolean
- Private Room Provided: boolean
- Driving Required: boolean
- Teaching Languages: array
- Minimum Degree: High School / Diploma / Associate Degree / Bachelor / Master / Doctorate
- Minimum Years of Relevant Experience: number
- Subjects: array
- Curriculum: array
- Early Years Experience: boolean
- Montessori Experience: boolean
- International School Experience: boolean
- Kindergarten Experience: boolean
- High-end Family Experience: boolean
- Private Tutoring Experience: boolean
- Nanny Educator Experience: boolean
- SEN / ADHD Experience: boolean
- Willing to Travel: boolean
- Cooking Required: boolean
- Baby Food Required: boolean
- Housekeeping Required: boolean
- School Pick-up Required: boolean
- Family-School Communication Required: boolean
- General Tutoring Experience: boolean
- Child Psychology Experience: boolean
- Luxury Hotel Experience: boolean
- Nutrition Planning: boolean
- Required Certificates: array of certificate names
- Exam Preparation: array, e.g. ["PET", "KET"]

REFERENCE ONLY:
- Child Ages: array of numeric ages in years. 18 months -> 1.5, 1 year 4 months -> 1.33.
Child ages must be placed in reference_requirements and must not be a hard rejection criterion.

MANUAL REVIEW ONLY (never automated ranking):
- Candidate Age Requirement
- Candidate Gender Preference
- Nationality / Hometown / Regional Preference
- Appearance / Height / Weight Preference
- Personality / Style Preference
- Education Institution / Major Preference
- Other Manual Review Notes

INTERPRETATION RULES:
1. Employer/family/job location -> Working Cities. District stays in Job District.
2. 住家 -> Live-in Required=true. 不住家 -> Live-in Job=false but do not require a teacher to be "non-live-in".
   住家/不住家均可 -> no Live-in Required.
3. 需要带睡 / 陪睡 / 夜间照护 / 偶尔夜间带睡 -> Night Care Required=true.
   不带睡 / 不用带睡 -> Night Care Required=false. Keep the information, but it should not restrict teachers.
4. 独立房间 / 老师有独立房间 / 提供独立房间 -> Private Room Provided=true.
5. 全英文 / 英语好 / 英语口语流利 / 全英授课 -> Teaching Languages=["English"].
6. 本科及以上 -> Minimum Degree="Bachelor". 研究生/硕士 -> "Master". 大专/专科及以上 -> "Associate Degree".
7. 早教 / 0-3岁早教 -> Early Years Experience=true.
8. 蒙氏 / Montessori -> Montessori Experience=true. If a Montessori certificate is explicitly required, also put it in Required Certificates.
9. 国际学校经历 -> International School Experience=true. 孩子就读国际学校 alone does NOT prove teacher experience; it can remain order context.
10. 幼儿园工作经历 -> Kindergarten Experience=true. If it says 幼儿园经历优先, put it in preferred_requirements.
11. 有真实上户经历 / 陪伴师经历 / 儿陪师经历 / 育儿师经历 -> Nanny Educator Experience=true. If a number of years is stated, also set Minimum Years of Relevant Experience.
12. ADHD / SEN child, when the teacher is expected to support that need -> SEN / ADHD Experience=true.
13. 全科辅导 -> General Tutoring Experience=true.
14. 家校对接 / 家校沟通 -> Family-School Communication Required=true.
15. 开车接送 / 熟练驾驶 -> Driving Required=true; 接送孩子 -> School Pick-up Required=true when driving/pickup is part of the job.
16. 跟随老板出差 -> Willing to Travel=true.
17. 辅食 -> Baby Food Required=true. 做饭/家常菜 -> Cooking Required=true. 家务/收纳 -> Housekeeping Required=true.
18. 营养搭配 -> Nutrition Planning=true.
19. 星级酒店从业经验 -> Luxury Hotel Experience=true.
20. PET/KET/AP/SAT exam preparation: put exam names under Exam Preparation when the job asks for exam preparation.
21. IB/AP/IGCSE/A-Level familiarity -> Curriculum array.
22. "最好/优先/优先考虑/ideally/preferred" -> preferred_requirements.
    Explicit "要求/必须/需要/工作内容必须完成" -> hard_requirements.
23. "无需家务/不做家务" means Housekeeping Required=false or simply omit it; it must never reject a teacher.
24. Job title such as 育儿师/儿陪师/家庭教师/私人助理/高端家务师 goes to Job Type only.
25. Do not invent qualifications that are not stated.
26. If input includes candidate age limits, gender, hometown exclusions, appearance, personality or similar personal traits, preserve them only in manual_review.

EMPLOYER ORDER:
{employer_request}
"""


def clean_json_text(text: str) -> str:
    """Remove markdown fences / leading prose while preserving JSON object OR array.

    V1.4 used a ``{.*}`` regex.  When Gemini returned a top-level JSON array
    such as ``[{...}, {...}]``, that regex removed the square brackets and
    produced invalid JSON.  This version keeps the original top-level JSON
    container.
    """
    cleaned = (
        str(text or "")
        .replace("```json", "")
        .replace("```JSON", "")
        .replace("```", "")
        .strip()
    )
    if not cleaned:
        return cleaned

    object_pos = cleaned.find("{")
    array_pos = cleaned.find("[")
    starts = [pos for pos in (object_pos, array_pos) if pos >= 0]
    if not starts:
        return cleaned

    start = min(starts)
    opening = cleaned[start]
    closing = "}" if opening == "{" else "]"
    end = cleaned.rfind(closing)
    if end < start:
        # Keep the content so json.loads can raise a useful decode error.
        return cleaned[start:]
    return cleaned[start : end + 1]


def normalize_requirement_group(group: Any) -> Tuple[Dict[str, Any], List[str]]:
    if not isinstance(group, dict):
        return {}, ["Gemini 返回的 requirement group 不是 dictionary。"]

    normalized: Dict[str, Any] = {}
    warnings: List[str] = []

    bool_fields = {
        "Live-in Required", "Night Care Required", "Private Room Provided", "Driving Required",
        "Early Years Experience", "Montessori Experience", "International School Experience",
        "Kindergarten Experience", "High-end Family Experience", "Private Tutoring Experience",
        "Nanny Educator Experience", "SEN / ADHD Experience", "Willing to Travel", "Cooking Required", "Baby Food Required",
        "Housekeeping Required", "School Pick-up Required", "Family-School Communication Required",
        "General Tutoring Experience", "Child Psychology Experience", "Luxury Hotel Experience",
        "Nutrition Planning",
    }
    list_fields = {"Working Cities", "Teaching Languages", "Subjects", "Curriculum", "Required Certificates", "Exam Preparation"}

    for field, value in group.items():
        if field not in ALLOWED_MATCH_FIELDS:
            warnings.append(f"忽略未支持的自动匹配字段：{field}")
            continue
        if value is None or value == "" or value == [] or value == {}:
            continue

        if field in bool_fields:
            state = boolish(value)
            if state is None:
                warnings.append(f"无法识别布尔字段 {field}: {value}")
                continue
            normalized[field] = state
        elif field == "Minimum Degree":
            degree = normalize_degree(value)
            if degree:
                normalized[field] = degree
        elif field == "Minimum Years of Relevant Experience":
            number = to_number(value)
            if number is not None:
                normalized[field] = number
        elif field == "Working Cities":
            cities = [normalize_city(x) for x in ensure_list(value)]
            normalized[field] = dedupe([x for x in cities if x])
        elif field in list_fields:
            normalized[field] = normalize_multi_text(value)
        else:
            normalized[field] = value

    return normalized, warnings


def normalize_reference_group(group: Any, order_info: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    normalized: Dict[str, Any] = {}
    if isinstance(group, dict):
        raw_ages = group.get("Child Ages")
        if raw_ages is None:
            raw_ages = group.get("Child Age")
        ages = [to_number(x) for x in ensure_list(raw_ages)]
        ages = [x for x in ages if x is not None]
        if ages:
            normalized["Child Ages"] = ages
    if "Child Ages" not in normalized:
        ages = [to_number(x) for x in ensure_list(order_info.get("Child Ages"))]
        ages = [x for x in ages if x is not None]
        if ages:
            normalized["Child Ages"] = ages
    return normalized, warnings


def normalize_order_info(info: Any) -> Dict[str, Any]:
    info = info if isinstance(info, dict) else {}
    cities = [normalize_city(x) for x in ensure_list(info.get("Working Cities"))]
    ages = [to_number(x) for x in ensure_list(info.get("Child Ages"))]
    return {
        "Order ID": info.get("Order ID"),
        "Job Type": info.get("Job Type"),
        "Working Cities": dedupe([x for x in cities if x]),
        "Job District": info.get("Job District"),
        "Salary Text": info.get("Salary Text"),
        "Work Schedule": info.get("Work Schedule"),
        "Start Date": info.get("Start Date"),
        "Live-in Job": boolish(info.get("Live-in Job")),
        "Child Ages": [x for x in ages if x is not None],
        "Child Count": int(to_number(info.get("Child Count"))) if to_number(info.get("Child Count")) is not None else None,
        "Special Needs": normalize_multi_text(info.get("Special Needs")),
    }


def normalize_manual_review(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        # Preserve model wording, but keep it in manual review only.
        if item is None or item == "" or item == [] or item == {}:
            continue
        result[str(key)] = item
    return result


def parse_employer_order(employer_request: str) -> Dict[str, Any]:
    request_text = str(employer_request or "").strip()
    if not request_text:
        raise ValueError("请输入一条雇主订单。")

    # Save Gemini quota when the single-order box clearly contains many orders.
    detected_orders = split_batch_orders(request_text)
    if len(detected_orders) > 1:
        raise ValueError(
            f"单单匹配框里检测到 {len(detected_orders)} 条订单。"
            "请切换到『② 批量订单 → 每单推荐老师』后再粘贴。"
        )

    client = gemini_client()
    prompt = build_parser_prompt(request_text)

    def generate(model_name: str):
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

    model_used = GEMINI_MODEL
    try:
        response = generate(model_used)
    except Exception as first_exc:
        # If the configured model was removed/unavailable, try one available Flash model once.
        text = str(first_exc)
        if "404" in text or "NOT_FOUND" in text or "not available" in text.lower():
            models = list_generate_models(client)
            alternatives = [m for m in models if "flash" in m.lower() and m != model_used]
            if alternatives:
                model_used = alternatives[0]
                response = generate(model_used)
            else:
                raise
        else:
            raise

    if not getattr(response, "text", None):
        raise RuntimeError("Gemini 返回了响应，但没有文本内容。")

    try:
        raw = json.loads(clean_json_text(response.text))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini 返回的 JSON 不完整或格式异常。请重新运行一次；"
            "如果粘贴的是多条订单，请使用批量匹配模式。"
        ) from exc

    # Gemini occasionally returns a top-level array even when ONE object was requested.
    if isinstance(raw, list):
        if len(raw) == 1 and isinstance(raw[0], dict):
            raw = raw[0]
        elif len(raw) > 1:
            raise ValueError(
                f"Gemini 在单单模式中识别出了 {len(raw)} 条订单。"
                "请切换到『② 批量订单 → 每单推荐老师』。"
            )

    # Also tolerate the batch wrapper when it contains exactly one order.
    if isinstance(raw, dict) and isinstance(raw.get("orders"), list):
        wrapped_orders = raw.get("orders", [])
        if len(wrapped_orders) == 1 and isinstance(wrapped_orders[0], dict):
            raw = wrapped_orders[0]
        elif len(wrapped_orders) > 1:
            raise ValueError(
                f"Gemini 在单单模式中识别出了 {len(wrapped_orders)} 条订单。"
                "请切换到『② 批量订单 → 每单推荐老师』。"
            )

    if not isinstance(raw, dict):
        raise RuntimeError("Gemini 单单解析返回的顶层内容不是 JSON object。")

    order_info = normalize_order_info(raw.get("order_info"))
    hard, w1 = normalize_requirement_group(raw.get("hard_requirements", {}))
    preferred, w2 = normalize_requirement_group(raw.get("preferred_requirements", {}))
    reference, w3 = normalize_reference_group(raw.get("reference_requirements", {}), order_info)
    manual_review = normalize_manual_review(raw.get("manual_review", {}))

    # Ensure location/live-in context becomes job-relevant matching data.
    # V1.6 source-grounding: identifiers, cities, district, job type, and child ages
    # are taken from the isolated source block whenever Python can read them directly.
    # This prevents cross-order contamination even if Gemini accidentally borrows a detail.
    source_order_id = extract_source_order_id(request_text)
    source_cities = extract_source_cities(request_text)
    source_child_ages = extract_source_child_ages(request_text)
    source_job_type = extract_source_job_type(request_text)
    source_district = extract_source_district(request_text)

    if source_order_id:
        order_info["Order ID"] = source_order_id
    if source_job_type:
        order_info["Job Type"] = source_job_type
    if source_district:
        order_info["Job District"] = source_district
    if source_cities:
        order_info["Working Cities"] = source_cities
        hard["Working Cities"] = source_cities
    elif order_info.get("Working Cities") and "Working Cities" not in hard:
        hard["Working Cities"] = order_info["Working Cities"]

    if source_child_ages:
        order_info["Child Ages"] = source_child_ages
        reference["Child Ages"] = source_child_ages

    if order_info.get("Live-in Job") is True and "Live-in Required" not in hard:
        hard["Live-in Required"] = True

    return {
        "original_request": request_text,
        "model_used": model_used,
        "order_info": order_info,
        "hard_requirements": hard,
        "preferred_requirements": preferred,
        "reference_requirements": reference,
        "manual_review": manual_review,
        "raw_requirements": raw,
        "warnings": w1 + w2 + w3,
    }


# ============================================================
# 6. MATCHER
# ============================================================

MATCH = "match"
CONFLICT = "conflict"
UNKNOWN = "unknown"
NOT_APPLICABLE = "not_applicable"

FIELD_LABELS = {
    "Working Cities": "工作城市",
    "Live-in Required": "住家",
    "Night Care Required": "带睡/夜间照护",
    "Private Room Provided": "独立房间",
    "Driving Required": "驾驶",
    "Teaching Languages": "工作语言",
    "Minimum Degree": "最低学历",
    "Minimum Years of Relevant Experience": "最低相关经验年限",
    "Subjects": "教学/辅导方向",
    "Curriculum": "课程体系",
    "Early Years Experience": "早教经验",
    "Montessori Experience": "蒙氏经验",
    "International School Experience": "国际学校经验",
    "Kindergarten Experience": "幼儿园工作经验",
    "High-end Family Experience": "高净值/高端家庭经验",
    "Private Tutoring Experience": "私人辅导经验",
    "Nanny Educator Experience": "儿陪/育儿/教育管家上户经验",
    "SEN / ADHD Experience": "SEN/ADHD经验",
    "Willing to Travel": "可出差",
    "Cooking Required": "烹饪",
    "Baby Food Required": "辅食制作",
    "Housekeeping Required": "家务/收纳",
    "School Pick-up Required": "接送孩子",
    "Family-School Communication Required": "家校沟通",
    "General Tutoring Experience": "全科辅导经验",
    "Child Psychology Experience": "儿童心理相关经验",
    "Luxury Hotel Experience": "星级酒店经验",
    "Nutrition Planning": "营养搭配",
    "Required Certificates": "所需证书",
    "Exam Preparation": "考试辅导",
    "Child Ages": "孩子年龄（参考）",
}

TEACHER_FIELD_MAP = {
    "Driving Required": "Driving",
    "Early Years Experience": "Early Years Experience",
    "Montessori Experience": "Montessori Experience",
    "International School Experience": "International School Experience",
    "Kindergarten Experience": "Kindergarten Experience",
    "High-end Family Experience": "High-end Family Experience",
    "Private Tutoring Experience": "Private Tutoring Experience",
    "Nanny Educator Experience": "Nanny Educator Experience",
    "SEN / ADHD Experience": "SEN Experience",
    "Willing to Travel": "Willing to Travel",
    "Cooking Required": "Cooking",
    "Baby Food Required": "Baby Food",
    "Housekeeping Required": "Housekeeping",
    "School Pick-up Required": "School Pick-up",
    "Family-School Communication Required": "Family-School Communication",
    "General Tutoring Experience": "General Tutoring Experience",
    "Child Psychology Experience": "Child Psychology Experience",
    "Luxury Hotel Experience": "Luxury Hotel Experience",
    "Nutrition Planning": "Nutrition Planning",
}


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def teacher_name(teacher: Dict[str, Any]) -> str:
    english_name = teacher.get("English Name") or teacher.get("Preferred Name")
    first = teacher.get("First Name") or ""
    last = teacher.get("Last Name") or ""
    base = " ".join(str(x).strip() for x in [first, last] if str(x).strip()).strip()
    if english_name and base:
        return f"{base} ({english_name})"
    if base:
        return base
    if teacher.get("Name"):
        return str(teacher.get("Name"))
    return f"Teacher {teacher.get('Baserow ID', '')}"


def teacher_list(teacher: Dict[str, Any], field: str) -> List[str]:
    return normalize_multi_text(teacher.get(field))


def teacher_evidence_text(teacher: Dict[str, Any]) -> str:
    """Build a conservative evidence string from resume-like Baserow fields.

    This does NOT invent experience.  It only lets the matcher recognize explicit
    words already present in profile / skills / certificates / subjects / notes.
    """
    fields = [
        "Skills", "Certificates", "Qualifications", "Major", "University",
        "Subjects", "Curriculum", "Experience Summary", "Profile", "Notes",
        "Desired Position", "Current Position",
    ]
    parts: List[str] = []
    for field in fields:
        value = teacher.get(field)
        if value is None or value == "":
            continue
        if isinstance(value, list):
            parts.extend(str(x) for x in value if x not in (None, ""))
        else:
            parts.append(str(value))
    return normalize_text(" | ".join(parts))


def evidence_keyword_match(teacher: Dict[str, Any], keywords: Iterable[str]) -> bool:
    haystack = teacher_evidence_text(teacher)
    if not haystack:
        return False
    return any(normalize_text(keyword) in haystack for keyword in keywords)


def match_boolean_teacher_field(
    teacher: Dict[str, Any],
    field: str,
    required: Any,
    *,
    false_is_unknown: bool = False,
) -> str:
    required_state = boolish(required)
    if required_state is not True:
        # Employer explicitly says a service is NOT required -> no restriction.
        return NOT_APPLICABLE
    actual = boolish(teacher.get(field))
    if actual is None:
        return UNKNOWN
    if actual is False and false_is_unknown:
        # Experience checkboxes are often blank-by-default in Baserow.  For these
        # fields, absence of evidence should be "待确认" rather than a hard conflict.
        return UNKNOWN
    return MATCH if actual is True else CONFLICT


def match_subset(actual_values: List[str], required_values: List[str]) -> str:
    if not required_values:
        return NOT_APPLICABLE
    if not actual_values:
        return UNKNOWN
    actual = {normalize_text(x) for x in actual_values}
    required = {normalize_text(x) for x in required_values}
    return MATCH if required.issubset(actual) else CONFLICT


def evaluate_requirement(teacher: Dict[str, Any], field: str, expected: Any) -> str:
    if field == "Working Cities":
        required = [normalize_city(x) for x in ensure_list(expected)]
        required = [x for x in required if x]
        preferred = [normalize_city(x) for x in teacher_list(teacher, "Preferred Cities")]
        preferred = [x for x in preferred if x]
        if not required:
            return NOT_APPLICABLE
        if not preferred:
            return UNKNOWN
        norm_preferred = {normalize_text(x) for x in preferred}
        if normalize_text("Any City") in norm_preferred:
            return MATCH
        # Multiple cities in one order are treated as acceptable / sequential work locations.
        # A teacher only needs at least one city overlap here. If the family truly requires
        # relocation across every listed city, the recruiter should confirm that manually.
        required_norm = {normalize_text(x) for x in required}
        return MATCH if required_norm.intersection(norm_preferred) else CONFLICT

    if field == "Live-in Required":
        return match_boolean_teacher_field(teacher, "Live-in", expected)

    if field == "Night Care Required":
        # Employer says "not required" = no restriction. If required, teacher must accept it.
        return match_boolean_teacher_field(teacher, "Night Care Accepted", expected)

    if field == "Private Room Provided":
        provided = boolish(expected)
        if provided is True:
            return MATCH
        if provided is None:
            return UNKNOWN
        teacher_requires = boolish(teacher.get("Private Room Required"))
        if teacher_requires is None:
            return UNKNOWN
        return CONFLICT if teacher_requires else MATCH

    if field == "Teaching Languages":
        return match_subset(teacher_list(teacher, "Teaching Languages"), normalize_multi_text(expected))

    if field == "Minimum Degree":
        required = normalize_degree(expected)
        actual = normalize_degree(teacher.get("Highest Degree"))
        if not required:
            return NOT_APPLICABLE
        if not actual or actual not in DEGREE_RANK:
            return UNKNOWN
        if required not in DEGREE_RANK:
            return UNKNOWN
        return MATCH if DEGREE_RANK[actual] >= DEGREE_RANK[required] else CONFLICT

    if field == "Minimum Years of Relevant Experience":
        required = to_number(expected)
        actual = to_number(teacher.get("Years of Teaching"))
        if required is None:
            return NOT_APPLICABLE
        if actual is None:
            return UNKNOWN
        return MATCH if actual >= required else CONFLICT

    if field == "Subjects":
        return match_subset(teacher_list(teacher, "Subjects"), normalize_multi_text(expected))

    if field == "Curriculum":
        return match_subset(teacher_list(teacher, "Curriculum"), normalize_multi_text(expected))

    if field == "Required Certificates":
        required = normalize_multi_text(expected)
        actual = teacher_list(teacher, "Certificates") or teacher_list(teacher, "Qualifications")
        if not required:
            return NOT_APPLICABLE
        if not actual:
            return UNKNOWN
        actual_norm = [normalize_text(x) for x in actual]
        for req in required:
            req_norm = normalize_text(req)
            if not any(req_norm in cert or cert in req_norm for cert in actual_norm):
                return CONFLICT
        return MATCH

    if field == "Exam Preparation":
        return match_subset(teacher_list(teacher, "Exam Preparation"), normalize_multi_text(expected))

    if field in TEACHER_FIELD_MAP:
        teacher_field = TEACHER_FIELD_MAP[field]

        # Conservative evidence fallbacks based on fields used in the Yan Li resume template.
        if field == "Early Years Experience":
            subjects = {normalize_text(x) for x in teacher_list(teacher, "Subjects")}
            if normalize_text("Early Years") in subjects or evidence_keyword_match(teacher, ["早教", "early years", "0-3岁"]):
                return MATCH

        if field == "Montessori Experience":
            curriculum = {normalize_text(x) for x in teacher_list(teacher, "Curriculum")}
            if normalize_text("Montessori") in curriculum or evidence_keyword_match(teacher, ["蒙氏", "montessori"]):
                return MATCH

        if field == "General Tutoring Experience":
            fallback = boolish(teacher.get("Private Tutoring Experience"))
            subjects = {normalize_text(x) for x in teacher_list(teacher, "Subjects")}
            if fallback is True or normalize_text("Primary Education") in subjects or evidence_keyword_match(teacher, ["全科辅导", "课后辅导", "学习辅导"]):
                return MATCH

        evidence_map = {
            "Kindergarten Experience": ["幼儿园工作", "kindergarten"],
            "High-end Family Experience": ["高净值家庭", "高端家庭", "private family"],
            "Private Tutoring Experience": ["私人辅导", "家教", "private tutoring"],
            "Nanny Educator Experience": ["教育管家", "儿陪师", "育儿师", "育婴师", "儿童陪伴", "nanny educator"],
            "SEN / ADHD Experience": ["adhd", "sen", "特殊教育", "特殊需求"],
            "Family-School Communication Required": ["家校沟通", "家校对接", "school communication"],
            "Child Psychology Experience": ["心理学", "心理咨询师", "psychology", "psychological counselor"],
            "Cooking Required": ["烹饪", "中餐", "西餐", "cooking"],
            "Baby Food Required": ["辅食"],
            "Housekeeping Required": ["家务", "收纳", "housekeeping"],
            "Luxury Hotel Experience": ["星级酒店", "luxury hotel"],
            "Nutrition Planning": ["营养搭配", "营养餐", "nutrition"],
        }
        if field in evidence_map and evidence_keyword_match(teacher, evidence_map[field]):
            return MATCH

        # Capabilities/availability where False is meaningful.
        strict_false_fields = {
            "Willing to Travel",
        }
        # Experience-style booleans: an unchecked/blank Baserow checkbox is treated
        # as unknown, not as proof that the teacher lacks the experience.
        false_is_unknown = field not in strict_false_fields
        return match_boolean_teacher_field(
            teacher,
            teacher_field,
            expected,
            false_is_unknown=false_is_unknown,
        )

    return UNKNOWN


def evaluate_group(teacher: Dict[str, Any], requirements: Dict[str, Any]) -> Dict[str, List[str]]:
    result = {MATCH: [], CONFLICT: [], UNKNOWN: [], NOT_APPLICABLE: []}
    for field, expected in requirements.items():
        outcome = evaluate_requirement(teacher, field, expected)
        result[outcome].append(field)
    return result


def evaluate_child_age_reference(teacher: Dict[str, Any], reference: Dict[str, Any]) -> Dict[str, List[str]]:
    result = {MATCH: [], CONFLICT: [], UNKNOWN: [], NOT_APPLICABLE: []}
    ages = [to_number(x) for x in ensure_list(reference.get("Child Ages"))]
    ages = [x for x in ages if x is not None]
    if not ages:
        result[NOT_APPLICABLE].append("Child Ages")
        return result

    minimum = to_number(teacher.get("Minimum Child Age"))
    maximum = to_number(teacher.get("Maximum Child Age"))
    if minimum is None and maximum is None:
        result[UNKNOWN].append("Child Ages")
        return result

    def accepted(age: float) -> bool:
        if minimum is not None and age < minimum:
            return False
        if maximum is not None and age > maximum:
            return False
        return True

    if all(accepted(age) for age in ages):
        result[MATCH].append("Child Ages")
    else:
        result[CONFLICT].append("Child Ages")
    return result


def group_total(group: Dict[str, List[str]]) -> int:
    return len(group[MATCH]) + len(group[CONFLICT]) + len(group[UNKNOWN])


def hard_coverage_ratio(group: Dict[str, List[str]]) -> Optional[float]:
    """For hard requirements, unknown data counts as not-yet-covered.

    Example: 3 matched + 3 unknown = 50%, never 100%.
    """
    total = group_total(group)
    if total == 0:
        return None
    return len(group[MATCH]) / total


def known_quality_ratio(group: Dict[str, List[str]]) -> Optional[float]:
    """For preferred/reference groups, score only evidence that is actually known."""
    known = len(group[MATCH]) + len(group[CONFLICT])
    if known == 0:
        return None
    return len(group[MATCH]) / known


def calculate_score(hard: Dict[str, List[str]], preferred: Dict[str, List[str]], reference: Dict[str, List[str]]) -> int:
    weighted: List[Tuple[float, float]] = []

    hard_ratio = hard_coverage_ratio(hard)
    if hard_ratio is not None:
        weighted.append((hard_ratio, HARD_WEIGHT))

    preferred_ratio = known_quality_ratio(preferred)
    if preferred_ratio is not None:
        weighted.append((preferred_ratio, PREFERRED_WEIGHT))

    reference_ratio = known_quality_ratio(reference)
    if reference_ratio is not None:
        weighted.append((reference_ratio, REFERENCE_WEIGHT))

    if not weighted:
        return 0

    total_weight = sum(weight for _, weight in weighted)
    return round(sum(ratio_value * weight for ratio_value, weight in weighted) / total_weight * 100)


def hard_status(hard: Dict[str, List[str]]) -> Tuple[str, int]:
    total = group_total(hard)
    if hard[CONFLICT]:
        return "conflict", 0
    if total == 0 or hard[UNKNOWN]:
        return "pending", 1
    return "confirmed", 2


def hard_confirmation_rate(hard: Dict[str, List[str]]) -> int:
    total = group_total(hard)
    if total == 0:
        return 0
    return round((len(hard[MATCH]) + len(hard[CONFLICT])) / total * 100)


def add_candidate_side_pending_checks(
    teacher: Dict[str, Any],
    order_info: Dict[str, Any],
    hard_requirements: Dict[str, Any],
    hard: Dict[str, List[str]],
) -> None:
    """Teacher-side requirements can create pending checks even if employer text omitted them."""
    live_in_job = hard_requirements.get("Live-in Required") is True or order_info.get("Live-in Job") is True
    if live_in_job and boolish(teacher.get("Private Room Required")) is True and "Private Room Provided" not in hard_requirements:
        if "Private Room Provided" not in hard[UNKNOWN]:
            hard[UNKNOWN].append("Private Room Provided")


def match_teacher(
    teacher: Dict[str, Any],
    parsed: Dict[str, Any],
) -> Dict[str, Any]:
    hard = evaluate_group(teacher, parsed.get("hard_requirements", {}))
    preferred = evaluate_group(teacher, parsed.get("preferred_requirements", {}))
    reference = evaluate_child_age_reference(teacher, parsed.get("reference_requirements", {}))
    add_candidate_side_pending_checks(teacher, parsed.get("order_info", {}), parsed.get("hard_requirements", {}), hard)

    status, status_rank = hard_status(hard)
    score = calculate_score(hard, preferred, reference)
    confirmation = hard_confirmation_rate(hard)

    reasons = []
    for field in hard[MATCH]:
        reasons.append(f"硬条件已确认：{field_label(field)}")
    for field in preferred[MATCH]:
        reasons.append(f"偏好已满足：{field_label(field)}")
    if "Child Ages" in reference[MATCH]:
        reasons.append("孩子年龄处于老师可接受年龄范围内（参考项）")

    return {
        "teacher": teacher,
        "name": teacher_name(teacher),
        "score": score,
        "confirmation": confirmation,
        "status": status,
        "status_rank": status_rank,
        "hard": hard,
        "preferred": preferred,
        "reference": reference,
        "reasons": reasons[:8],
    }


def run_matching(teachers: List[Dict[str, Any]], parsed: Dict[str, Any], top_n: int = TOP_N) -> List[Dict[str, Any]]:
    results = [match_teacher(teacher, parsed) for teacher in teachers]
    results.sort(
        key=lambda item: (
            item["status_rank"],
            item["score"],
            item["confirmation"],
            to_number(item["teacher"].get("Years of Teaching")) or 0,
        ),
        reverse=True,
    )
    return results[:top_n]


# ============================================================
# 7. DISPLAY HELPERS
# ============================================================


def requirement_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return ", ".join(str(x) for x in value) if value else "无"
    return str(value)


def render_requirement_group(title: str, group: Dict[str, Any]) -> None:
    st.markdown(f"#### {title}")
    if not group:
        st.caption("无")
        return
    for field, value in group.items():
        st.write(f"**{field_label(field)}：** {requirement_value(value)}")


def render_order_info(info: Dict[str, Any]) -> None:
    st.markdown("#### 订单信息")
    display = {
        "订单编号": info.get("Order ID"),
        "岗位": info.get("Job Type"),
        "工作城市": format_list(info.get("Working Cities")),
        "区域": info.get("Job District"),
        "薪资": info.get("Salary Text"),
        "工作时间": info.get("Work Schedule"),
        "到岗时间": info.get("Start Date"),
        "住家岗位": tri_text(info.get("Live-in Job")),
        "孩子年龄": format_list(info.get("Child Ages")),
        "孩子数量": info.get("Child Count"),
        "特殊需求": format_list(info.get("Special Needs")),
    }
    for label, value in display.items():
        if value not in (None, "", "未填写"):
            st.write(f"**{label}：** {value}")


def render_outcomes(title: str, group: Dict[str, List[str]]) -> None:
    st.markdown(f"#### {title}")
    st.write("✅ **已确认匹配：**", ", ".join(field_label(x) for x in group[MATCH]) or "无")
    st.write("❌ **已确认不匹配：**", ", ".join(field_label(x) for x in group[CONFLICT]) or "无")
    st.write("⚠️ **待确认：**", ", ".join(field_label(x) for x in group[UNKNOWN]) or "无")


def render_teacher_card(rank: int, item: Dict[str, Any]) -> None:
    teacher = item["teacher"]
    with st.container(border=True):
        left, right = st.columns([4, 1])
        with left:
            st.markdown(f"### {rank}. {item['name']}")
            if item["status"] == "confirmed":
                st.success("✅ 岗位硬条件已确认匹配")
            elif item["status"] == "pending":
                st.warning("⚠️ 没有明确冲突，但部分硬条件需要人工确认")
            else:
                st.error("❌ 存在已确认的岗位硬条件冲突")
        with right:
            st.metric("岗位匹配度", f"{item['score']}%")
            st.caption(f"硬条件资料确认度：{item['confirmation']}%")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**年龄（仅展示，不参与自动排名）：**", format_number(teacher.get("Age")))
            st.write("**国籍（仅展示，不参与自动排名）：**", teacher.get("Nationality") or "未填写")
            current = ", ".join(str(x) for x in [teacher.get("Current City"), teacher.get("Current Country")] if x)
            st.write("**当前所在地：**", current or "未填写")
            st.write("**最高学历：**", teacher.get("Highest Degree") or "未填写")
            st.write("**相关经验年限：**", format_number(teacher.get("Years of Teaching")))
        with c2:
            st.write("**可接受工作城市：**", format_list(teacher.get("Preferred Cities")))
            min_age = to_number(teacher.get("Minimum Child Age"))
            max_age = to_number(teacher.get("Maximum Child Age"))
            if min_age is None and max_age is None:
                child_range = "未填写"
            elif min_age is not None and max_age is None:
                child_range = f"{format_number(min_age)}岁以上"
            elif min_age is None and max_age is not None:
                child_range = f"{format_number(max_age)}岁以下"
            else:
                child_range = f"{format_number(min_age)}–{format_number(max_age)}岁"
            st.write("**可接受孩子年龄：**", child_range)
            st.write("**教学/工作语言：**", format_list(teacher.get("Teaching Languages")))
            st.write("**签证国家：**", format_list(teacher.get("Visa Countries")))
            st.write("**工作许可国家：**", format_list(teacher.get("Work Authorization Countries")))
            st.write("**Subjects：**", format_list(teacher.get("Subjects")))
            st.write("**Curriculum：**", format_list(teacher.get("Curriculum")))
        with c3:
            st.write("**可住家：**", tri_text(teacher.get("Live-in")))
            st.write("**接受带睡：**", tri_text(teacher.get("Night Care Accepted")))
            st.write("**要求独立房间：**", tri_text(teacher.get("Private Room Required")))
            st.write("**驾驶：**", tri_text(teacher.get("Driving")))
            st.write("**可出差：**", tri_text(teacher.get("Willing to Travel")))

        st.divider()
        render_outcomes("硬条件", item["hard"])
        with st.expander("偏好与参考适配"):
            render_outcomes("偏好条件", item["preferred"])
            render_outcomes("孩子年龄参考", item["reference"])
        if item["reasons"]:
            st.markdown("#### 推荐理由")
            for reason in item["reasons"]:
                st.write(f"• {reason}")
        with st.expander("查看完整老师资料"):
            clean = {k: v for k, v in teacher.items() if not str(k).startswith("_")}
            st.json(clean)



# ============================================================
# 8. BATCH PARSER / BATCH MATCHING HELPERS
# ============================================================


def extract_source_order_id(text: str) -> Optional[str]:
    """Extract an explicit recruiter order ID from the source text itself.

    Source text wins over Gemini for this field because order IDs are identifiers,
    not semantic interpretations.
    """
    source = str(text or "")
    patterns = [
        r"【\s*(?:订单\s*(?:编号|编码)|订单号|编号)\s*】\s*[:：]?\s*([^\s，,；;。\n]+)",
        r"(?:订单\s*(?:编号|编码)|订单号|编号)\s*[:：]\s*([^\s，,；;。\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip("：:[]【】()（）")
            if value:
                return value

    # Recruiter codes often appear without an explicit label.
    code_match = re.search(r"\b(?:HX[CWQG]|HG|ZJS)[A-Z0-9ⅩX-]{5,}\b", source, flags=re.IGNORECASE)
    if code_match:
        return code_match.group(0).strip()
    return None


def extract_source_cities(text: str) -> List[str]:
    """Find standardized cities that are literally present in one source block."""
    source = str(text or "")
    found: List[Tuple[int, str]] = []
    for alias, standard in CITY_ALIASES.items():
        # Ignore wildcard aliases for source location extraction.
        if standard == "Any City":
            continue
        for match in re.finditer(re.escape(alias), source, flags=re.IGNORECASE):
            found.append((match.start(), standard))
        # Also accept the standardized English name when recruiters paste bilingual text.
        if normalize_text(alias) != normalize_text(standard):
            for match in re.finditer(re.escape(standard), source, flags=re.IGNORECASE):
                found.append((match.start(), standard))
    found.sort(key=lambda pair: pair[0])
    return dedupe([standard for _, standard in found])


def extract_source_child_ages(text: str) -> List[float]:
    """Conservatively extract CHILD ages from source text.

    Candidate age limits such as "40岁以内" are intentionally excluded.
    """
    source = str(text or "")
    child_words = ("宝", "宝宝", "孩子", "男孩", "女孩", "男宝", "女宝", "哥哥", "妹妹", "学生", "儿童")
    candidate_words = ("老师", "阿姨", "育儿师", "陪伴师", "儿陪师", "家务师", "年龄", "周岁以内", "周岁以下")
    results: List[float] = []

    age_pattern = re.compile(
        r"(?P<years>\d+(?:\.\d+)?)\s*岁(?:\s*(?P<half>半)|\s*(?P<months>\d+)\s*个?月)?|(?P<onlymonths>\d+(?:\.\d+)?)\s*个?月(?!份)"
    )
    for match in age_pattern.finditer(source):
        left = max(0, match.start() - 14)
        right = min(len(source), match.end() + 14)
        window = source[left:right]
        if not any(word in window for word in child_words):
            continue
        if any(word in window for word in candidate_words) and not any(
            word in window for word in ("宝宝", "孩子", "男孩", "女孩", "男宝", "女宝", "学生")
        ):
            continue
        immediate_after = source[match.end() : match.end() + 6]
        if re.match(r"\s*(?:以内|以下|以上|之间)", immediate_after):
            continue

        # A months-only age should be close to a child noun; this avoids
        # treating phrases such as "9月份入学" as a 9-month-old child.
        if match.group("onlymonths") is not None:
            near = source[max(0, match.start() - 8) : min(len(source), match.end() + 8)]
            if not any(word in near for word in child_words):
                continue
            age = float(match.group("onlymonths")) / 12.0
        else:
            age = float(match.group("years"))
            if match.group("half"):
                age += 0.5
            if match.group("months"):
                age += float(match.group("months")) / 12.0
        results.append(round(age, 2))
    return dedupe(results)


def extract_source_job_type(text: str) -> Optional[str]:
    source = str(text or "")
    job_types = [
        "私人助理", "家庭教师", "蒙氏老师", "教育管家", "高端家务师",
        "儿陪师", "住家陪伴师", "陪伴师", "育儿师", "育婴师", "家务师", "家教",
    ]
    for job_type in job_types:
        if job_type in source:
            return job_type
    return None


def extract_source_district(text: str) -> Optional[str]:
    source = str(text or "")
    # Prefer labelled address/district text.
    labelled = re.search(
        r"(?:地址|工作地点|工作地址|区域)\s*[:：]?\s*[^\n]{0,25}?([\u4e00-\u9fff]{2,8}(?:区|县))",
        source,
    )
    if labelled:
        return labelled.group(1)

    generic = re.search(r"([\u4e00-\u9fff]{2,8}(?:区|县))", source)
    return generic.group(1) if generic else None


def source_block_complete(text: str) -> bool:
    """Heuristic: has enough independent evidence to represent a full order."""
    source = str(text or "")
    if len(source.strip()) < 25:
        return False
    score = 0
    if extract_source_cities(source) or re.search(r"工作(?:地点|地址)|城市\s*[:：]", source):
        score += 1
    if extract_source_job_type(source) or re.search(r"工作内容|内容\s*[:：]", source):
        score += 1
    if re.search(
        r"工作要求|老师要求|要求\s*[:：]|备注【|备注\s*[:：]|"
        r"岁以内|岁以下|本科|专科|硕士|研究生|英语|口语|驾驶|会开车|经验",
        source,
    ):
        score += 1
    if re.search(r"薪资|工资|待遇|\b\d{4,6}\s*[-~～—–]\s*\d{4,6}\b", source):
        score += 1
    if extract_source_order_id(source):
        score += 1
    if re.search(r"上户时间|到岗时间|随时上户|合适即上户|立即上户|尽快", source):
        score += 1
    return score >= 3


def line_looks_like_new_order(line: str, current_text: str) -> bool:
    """Return True only for a strong order-start line after a complete prior order."""
    stripped = line.strip()
    if not stripped:
        return False

    # Repeated recruiter header is always a new order once prior content exists.
    if re.search(r"沪上睿知派单中心\s*[:：]?", stripped):
        return bool(current_text.strip())

    # Strong hype / new-order markers used by recruiter groups.
    if re.match(r"^(?:十万火急|神仙级雇主|急急急|急单|新单|好单|推荐好单|🔥|🌈)", stripped):
        return source_block_complete(current_text)

    explicit_id = bool(
        re.search(
            r"(?:【\s*(?:订单\s*(?:编号|编码)|订单号|编号)\s*】|(?:订单\s*(?:编号|编码)|订单号|编号)\s*[:：])",
            stripped,
            flags=re.IGNORECASE,
        )
    )
    code_near_start = bool(
        re.match(r"^\s*(?:HX[CWQG]|HG|ZJS)[A-Z0-9ⅩX-]{5,}", stripped, flags=re.IGNORECASE)
    )

    # Salary lines are often the first line of a fresh recruiter order.
    salary_start = bool(re.match(r"^\s*(?:薪资|工资|待遇)\s*[:：]", stripped))

    # Location + living arrangement + role headline is another common order start.
    city_headline = bool(extract_source_cities(stripped)) and bool(
        re.search(r"住家|不住家|白班|育儿师|育婴师|儿陪师|陪伴师|家庭教师|家务师|私人助理|家教", stripped)
    )

    if not source_block_complete(current_text):
        return False

    if explicit_id or code_near_start:
        return True
    if salary_start and (extract_source_order_id(stripped) or city_headline):
        return True
    if city_headline and len(stripped) >= 16:
        return True
    return False


def split_batch_orders(batch_text: str) -> List[str]:
    """Deterministically split messy recruiter text BEFORE Gemini sees it.

    V1.6 uses a line-state machine instead of a single regex. It supports mixed
    formats where some orders have IDs, some start with salary, and some start
    with hype/location headlines. Gemini never decides order boundaries.
    """
    text = (
        str(batch_text or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u200b", "")
        .strip()
    )
    if not text:
        return []

    # First handle repeated dispatch-center markers even when they are pasted
    # in a long paragraph rather than on their own lines.
    dispatch_positions = [m.start() for m in re.finditer(r"(?=沪上睿知派单中心\s*[:：]?)", text)]
    if len(dispatch_positions) >= 2:
        blocks = []
        prefix = text[: dispatch_positions[0]].strip()
        for index, start in enumerate(dispatch_positions):
            end = dispatch_positions[index + 1] if index + 1 < len(dispatch_positions) else len(text)
            block = text[start:end].strip()
            if index == 0 and prefix:
                block = f"{prefix}\n{block}".strip()
            if block:
                blocks.append(block)
        return blocks

    lines = text.split("\n")
    blocks: List[str] = []
    current: List[str] = []

    for raw_line in lines:
        line = raw_line.rstrip()
        current_text = "\n".join(current).strip()

        if line_looks_like_new_order(line, current_text):
            if current_text:
                blocks.append(current_text)
            current = [line]
            continue

        # Separator lines can finish a complete order.
        if re.match(r"^\s*(?:={3,}|-{3,}|#{3,})\s*$", line):
            if current_text and source_block_complete(current_text):
                blocks.append(current_text)
                current = []
            continue

        current.append(line)

    tail = "\n".join(current).strip()
    if tail:
        blocks.append(tail)

    # Second pass: if a block still contains more than one explicit order ID,
    # split at later ID lines only when the preceding segment already looks complete.
    refined: List[str] = []
    for block in blocks:
        sublines = block.split("\n")
        subcurrent: List[str] = []
        for line in sublines:
            before = "\n".join(subcurrent).strip()
            explicit_id = bool(
                re.search(
                    r"(?:【\s*(?:订单\s*(?:编号|编码)|订单号|编号)\s*】|(?:订单\s*(?:编号|编码)|订单号|编号)\s*[:：])",
                    line,
                    flags=re.IGNORECASE,
                )
            )
            if explicit_id and before and extract_source_order_id(before) and source_block_complete(before):
                refined.append(before)
                subcurrent = [line]
            else:
                subcurrent.append(line)
        remainder = "\n".join(subcurrent).strip()
        if remainder:
            refined.append(remainder)

    return [block for block in refined if block.strip()]


def order_block_preview(block: str, index: int) -> Dict[str, Any]:
    cities = extract_source_cities(block)
    ages = extract_source_child_ages(block)
    first_lines = [line.strip() for line in block.splitlines() if line.strip()]
    snippet = " / ".join(first_lines[:2])
    if len(snippet) > 90:
        snippet = snippet[:90] + "…"
    return {
        "序号": index,
        "订单编号": extract_source_order_id(block) or "未识别",
        "城市": ", ".join(cities) if cities else "待 Gemini 识别",
        "岗位": extract_source_job_type(block) or "待 Gemini 识别",
        "孩子年龄": ", ".join(str(x) for x in ages) if ages else "待 Gemini 识别",
        "字符数": len(block),
        "原文开头": snippet,
    }


def preview_order_blocks(blocks: List[str]) -> List[Dict[str, Any]]:
    return [order_block_preview(block, index) for index, block in enumerate(blocks, start=1)]

def build_batch_parser_prompt(order_blocks: List[str]) -> str:
    numbered_orders = "\n\n".join(
        f"===== SOURCE ORDER {index} =====\n{block}"
        for index, block in enumerate(order_blocks, start=1)
    )

    return f"""
You parse MULTIPLE private-family recruitment orders into structured JSON.
Return JSON only. Do not include markdown.

There are exactly {len(order_blocks)} numbered source orders below.
Each SOURCE ORDER block is already split by Python and is authoritative.
Do not merge, split, reorder, or borrow any detail from another SOURCE ORDER.
Return exactly {len(order_blocks)} objects, one per source order, using its exact Source Index.

IMPORTANT EMPLOYMENT-SAFETY RULE:
Candidate age, gender, nationality/hometown/regional exclusions, appearance, height/weight,
and personality/style preferences must NEVER be placed in hard_requirements or preferred_requirements.
Preserve them only under manual_review for a human recruiter. They must not affect automated ranking.

RETURN THIS TOP-LEVEL STRUCTURE:
{{
  "orders": [
    {{
      "Source Index": 1,
      "order_info": {{
        "Order ID": null,
        "Job Type": null,
        "Working Cities": [],
        "Job District": null,
        "Salary Text": null,
        "Work Schedule": null,
        "Start Date": null,
        "Live-in Job": null,
        "Child Ages": [],
        "Child Count": null,
        "Special Needs": []
      }},
      "hard_requirements": {{}},
      "preferred_requirements": {{}},
      "reference_requirements": {{}},
      "manual_review": {{}}
    }}
  ]
}}

AUTOMATED MATCHING FIELDS ALLOWED IN hard_requirements / preferred_requirements:
- Working Cities: array of standardized English city names
- Live-in Required: boolean
- Night Care Required: boolean
- Private Room Provided: boolean
- Driving Required: boolean
- Teaching Languages: array
- Minimum Degree: High School / Diploma / Associate Degree / Bachelor / Master / Doctorate
- Minimum Years of Relevant Experience: number
- Subjects: array
- Curriculum: array
- Early Years Experience: boolean
- Montessori Experience: boolean
- International School Experience: boolean
- Kindergarten Experience: boolean
- High-end Family Experience: boolean
- Private Tutoring Experience: boolean
- Nanny Educator Experience: boolean
- SEN / ADHD Experience: boolean
- Willing to Travel: boolean
- Cooking Required: boolean
- Baby Food Required: boolean
- Housekeeping Required: boolean
- School Pick-up Required: boolean
- Family-School Communication Required: boolean
- General Tutoring Experience: boolean
- Child Psychology Experience: boolean
- Luxury Hotel Experience: boolean
- Nutrition Planning: boolean
- Required Certificates: array
- Exam Preparation: array

REFERENCE ONLY:
- Child Ages: array of numeric ages in years. 18 months -> 1.5, 1 year 4 months -> 1.33.
Child ages must not become a hard rejection criterion.

MANUAL REVIEW ONLY, NEVER AUTOMATED RANKING:
- Candidate Age Requirement
- Candidate Gender Preference
- Nationality / Hometown / Regional Preference
- Appearance / Height / Weight Preference
- Personality / Style Preference
- Education Institution / Major Preference
- Other Manual Review Notes

INTERPRETATION RULES:
1. Employer/family/job location -> Working Cities. District stays in Job District.
2. 住家 -> Live-in Required=true. 不住家 -> Live-in Job=false but do not require a teacher to be non-live-in.
   住家/不住家均可 -> no Live-in Required.
3. 需要带睡 / 陪睡 / 夜间照护 / 偶尔夜间带睡 -> Night Care Required=true.
   不带睡 / 不用带睡 -> Night Care Required=false; preserve it, but it must not reject a teacher.
4. 独立房间 / 老师有独立房间 / 提供独立房间 -> Private Room Provided=true.
5. 全英文 / 英语好 / 英语口语流利 / 全英授课 -> Teaching Languages=["English"].
6. 本科及以上 -> Minimum Degree="Bachelor". 研究生/硕士 -> "Master". 大专/专科及以上 -> "Associate Degree".
7. 早教 / 0-3岁早教 -> Early Years Experience=true.
8. 蒙氏 / Montessori -> Montessori Experience=true. If a Montessori certificate is explicitly required, add it to Required Certificates.
9. 国际学校经历 -> International School Experience=true. A child merely attending an international school is only order context.
10. 幼儿园工作经历 -> Kindergarten Experience=true. If it says 幼儿园经历优先, put it in preferred_requirements.
11. 有真实上户经历 / 陪伴师经历 / 儿陪师经历 / 育儿师经历 -> Nanny Educator Experience=true. If a number of years is stated, also set Minimum Years of Relevant Experience.
12. ADHD / SEN child, when the teacher is expected to support that need -> SEN / ADHD Experience=true.
13. 全科辅导 -> General Tutoring Experience=true.
14. 家校对接 / 家校沟通 -> Family-School Communication Required=true.
15. 开车接送 / 熟练驾驶 -> Driving Required=true. 接送孩子 -> School Pick-up Required=true when pickup is part of the job.
16. 跟随老板出差 -> Willing to Travel=true.
17. 辅食 -> Baby Food Required=true. 做饭/家常菜 -> Cooking Required=true. 家务/收纳 -> Housekeeping Required=true.
18. 营养搭配 -> Nutrition Planning=true.
19. 星级酒店从业经验 -> Luxury Hotel Experience=true.
20. PET/KET/AP/SAT exam preparation -> Exam Preparation.
21. IB/AP/IGCSE/A-Level familiarity -> Curriculum.
22. "最好/优先/优先考虑" -> preferred_requirements. Explicit "要求/必须/需要" -> hard_requirements.
23. "无需家务/不做家务" may be Housekeeping Required=false or omitted, and must never reject a teacher.
24. Job title such as 育儿师/儿陪师/家庭教师/私人助理/高端家务师 goes to Job Type only.
25. Do not invent qualifications not stated.
26. Candidate age limits, gender, hometown exclusions, appearance, personality, and similar personal traits go only to manual_review.

SOURCE ORDERS:
{numbered_orders}
"""


def generate_json_prompt(prompt: str) -> Tuple[Dict[str, Any], str]:
    """Run one Gemini JSON generation call with model fallback.

    Batch mode accepts both the requested ``{"orders": [...]}`` wrapper and a
    bare top-level array, because Gemini may occasionally omit the wrapper.
    """
    client = gemini_client()

    def generate(model_name: str):
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

    model_used = GEMINI_MODEL
    try:
        response = generate(model_used)
    except Exception as first_exc:
        text = str(first_exc)
        if "404" in text or "NOT_FOUND" in text or "not available" in text.lower():
            models = list_generate_models(client)
            alternatives = [m for m in models if "flash" in m.lower() and m != model_used]
            if alternatives:
                model_used = alternatives[0]
                response = generate(model_used)
            else:
                raise
        else:
            raise

    if not getattr(response, "text", None):
        raise RuntimeError("Gemini 返回了响应，但没有文本内容。")

    try:
        payload = json.loads(clean_json_text(response.text))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini 本批次返回的 JSON 不完整或格式异常。"
            "系统已限制每批订单数量；请重新运行一次。"
        ) from exc

    if isinstance(payload, list):
        payload = {"orders": payload}
    elif isinstance(payload, dict) and "orders" not in payload and "order_info" in payload:
        payload = {"orders": [payload]}

    if not isinstance(payload, dict):
        raise RuntimeError("Gemini 批量解析返回的顶层内容不是 JSON object 或 array。")

    return payload, model_used


def normalize_parsed_order_from_raw(
    raw: Dict[str, Any],
    original_request: str,
    model_used: str,
) -> Dict[str, Any]:
    """Normalize one order object returned from a batch Gemini request."""
    order_info = normalize_order_info(raw.get("order_info"))
    hard, w1 = normalize_requirement_group(raw.get("hard_requirements", {}))
    preferred, w2 = normalize_requirement_group(raw.get("preferred_requirements", {}))
    reference, w3 = normalize_reference_group(raw.get("reference_requirements", {}), order_info)
    manual_review = normalize_manual_review(raw.get("manual_review", {}))

    # V1.6 source-grounding: identifiers, cities, district, job type, and child ages
    # are taken from the isolated source block whenever Python can read them directly.
    # This prevents cross-order contamination even if Gemini accidentally borrows a detail.
    source_order_id = extract_source_order_id(original_request)
    source_cities = extract_source_cities(original_request)
    source_child_ages = extract_source_child_ages(original_request)
    source_job_type = extract_source_job_type(original_request)
    source_district = extract_source_district(original_request)

    if source_order_id:
        order_info["Order ID"] = source_order_id
    if source_job_type:
        order_info["Job Type"] = source_job_type
    if source_district:
        order_info["Job District"] = source_district
    if source_cities:
        order_info["Working Cities"] = source_cities
        hard["Working Cities"] = source_cities
    elif order_info.get("Working Cities") and "Working Cities" not in hard:
        hard["Working Cities"] = order_info["Working Cities"]

    if source_child_ages:
        order_info["Child Ages"] = source_child_ages
        reference["Child Ages"] = source_child_ages

    if order_info.get("Live-in Job") is True and "Live-in Required" not in hard:
        hard["Live-in Required"] = True

    return {
        "original_request": original_request,
        "model_used": model_used,
        "order_info": order_info,
        "hard_requirements": hard,
        "preferred_requirements": preferred,
        "reference_requirements": reference,
        "manual_review": manual_review,
        "raw_requirements": raw,
        "warnings": w1 + w2 + w3,
    }



# ============================================================
# 8B. V1.7 AI ORDER STANDARDIZATION LAYER
# ============================================================

STANDARD_ORDER_START = "===== ORDER START ====="
STANDARD_ORDER_END = "===== ORDER END ====="


def build_order_standardizer_prompt(raw_text: str) -> str:
    """Ask Gemini to convert mixed-platform recruiter text into ONE canonical schema.

    Gemini is allowed to identify semantic order boundaries here.  After this step,
    every order is written in a fixed machine-readable format and can be reviewed /
    edited by the recruiter before any matching starts.  The matching stage itself
    does not call Gemini again.
    """
    return f"""
You are an ORDER NORMALIZER for a private-family education / childcare recruitment system.
The input may contain MANY employer orders copied from DIFFERENT platforms, WeChat groups,
recruiters, agencies, plain messages, or partially structured forms. Their formatting is NOT reliable.

YOUR JOB:
1. Identify every DISTINCT employer order semantically.
2. Never merge unrelated orders merely because there is no blank line or common order-number format.
3. Convert every distinct order into the exact canonical JSON schema below.
4. Do NOT rank teachers and do NOT infer candidate capabilities.
5. Return JSON only. No markdown and no prose outside JSON.

ORDER-BOUNDARY RULES:
- Different order IDs usually mean different orders.
- A fresh combination of salary + city/location + job type + duties/requirements usually starts a new order.
- If the text clearly changes to another family, child, city, salary, job type, or work schedule, start a new order.
- A single order may legitimately contain multiple sequential/alternative cities, e.g. "长沙/新加坡". Keep those cities together ONLY when the source clearly says the same family/job works across those locations.
- Do not combine two separate families just because they are pasted on the same line.
- If an order has no ID, create no fake ID; keep Order ID as null.
- Do not invent missing information. Use null, [], or omit the requirement when not stated.

EMPLOYMENT-SAFETY RULE:
Candidate age, gender, nationality/hometown/regional exclusions, appearance, height/weight,
and personality/style preferences must NEVER affect automated ranking. Preserve them only
inside manual_review for a human recruiter.

RETURN EXACTLY:
{{
  "orders": [
    {{
      "source_excerpt": "a short excerpt that lets a human recognize this source order",
      "order_info": {{
        "Order ID": null,
        "Job Type": null,
        "Working Cities": [],
        "Job District": null,
        "Salary Text": null,
        "Work Schedule": null,
        "Start Date": null,
        "Live-in Job": null,
        "Child Ages": [],
        "Child Count": null,
        "Special Needs": []
      }},
      "hard_requirements": {{}},
      "preferred_requirements": {{}},
      "reference_requirements": {{}},
      "manual_review": {{}}
    }}
  ]
}}

AUTOMATED MATCHING FIELDS ALLOWED in hard_requirements / preferred_requirements:
- Working Cities: array of standardized English city names
- Live-in Required: boolean
- Night Care Required: boolean
- Private Room Provided: boolean
- Driving Required: boolean
- Teaching Languages: array
- Minimum Degree: High School / Diploma / Associate Degree / Bachelor / Master / Doctorate
- Minimum Years of Relevant Experience: number
- Subjects: array
- Curriculum: array
- Early Years Experience: boolean
- Montessori Experience: boolean
- International School Experience: boolean
- Kindergarten Experience: boolean
- High-end Family Experience: boolean
- Private Tutoring Experience: boolean
- Nanny Educator Experience: boolean
- SEN / ADHD Experience: boolean
- Willing to Travel: boolean
- Cooking Required: boolean
- Baby Food Required: boolean
- Housekeeping Required: boolean
- School Pick-up Required: boolean
- Family-School Communication Required: boolean
- General Tutoring Experience: boolean
- Child Psychology Experience: boolean
- Luxury Hotel Experience: boolean
- Nutrition Planning: boolean
- Required Certificates: array
- Exam Preparation: array

REFERENCE ONLY:
- Child Ages: numeric ages in years, e.g. 18 months -> 1.5; 1 year 4 months -> 1.33.
- Child Ages must appear in reference_requirements and must NEVER hard-reject a teacher.

MANUAL REVIEW ONLY, NEVER AUTOMATED RANKING:
- Candidate Age Requirement
- Candidate Gender Preference
- Nationality / Hometown / Regional Preference
- Appearance / Height / Weight Preference
- Personality / Style Preference
- Education Institution / Major Preference
- Other Manual Review Notes

INTERPRETATION RULES:
1. Employer/family/job location -> Working Cities. District stays in Job District.
2. 住家 -> Live-in Required=true and Live-in Job=true.
   不住家 -> Live-in Job=false; do not require a teacher to be "non-live-in".
   住家/不住家均可 -> no Live-in Required.
3. 需要带睡 / 陪睡 / 夜间照护 / 偶尔夜间带睡 -> Night Care Required=true.
   不带睡 / 不用带睡 -> Night Care Required=false; preserve it but it must not reject teachers.
4. 独立房间 / 老师有独立房间 / 提供独立房间 -> Private Room Provided=true.
5. 全英文 / 英语好 / 英语口语流利 / 全英授课 -> Teaching Languages=["English"].
6. 本科及以上 -> Minimum Degree="Bachelor"; 研究生/硕士 -> "Master"; 大专/专科及以上 -> "Associate Degree".
7. 早教 / 0-3岁早教 -> Early Years Experience=true.
8. 蒙氏 / Montessori -> Montessori Experience=true. Explicit Montessori certificate requirement -> Required Certificates.
9. 国际学校经历 -> International School Experience=true. Child attending international school alone is context, not teacher experience.
10. 幼儿园工作经历 -> Kindergarten Experience=true; "优先" goes to preferred_requirements.
11. 真实上户/陪伴师/儿陪师/育儿师/教育管家经历 -> Nanny Educator Experience=true. Stated years -> Minimum Years of Relevant Experience.
12. ADHD / SEN child requiring support -> SEN / ADHD Experience=true.
13. 全科辅导 -> General Tutoring Experience=true.
14. 家校对接 / 家校沟通 -> Family-School Communication Required=true.
15. 熟练驾驶 / 开车接送 -> Driving Required=true; child pickup/dropoff -> School Pick-up Required=true.
16. 跟随老板出差 -> Willing to Travel=true.
17. 辅食 -> Baby Food Required=true; 做饭/家常菜 -> Cooking Required=true; 家务/收纳 -> Housekeeping Required=true.
18. 营养搭配 -> Nutrition Planning=true.
19. 星级酒店从业经验 -> Luxury Hotel Experience=true.
20. PET/KET/AP/SAT exam preparation -> Exam Preparation.
21. IB/AP/IGCSE/A-Level familiarity -> Curriculum.
22. "最好/优先/优先考虑" -> preferred_requirements; explicit "要求/必须/需要" -> hard_requirements.
23. "无需家务/不做家务" may be Housekeeping Required=false or omitted; it must never reject a teacher.
24. Job titles such as 育儿师/儿陪师/家庭教师/私人助理/高端家务师 go to Job Type only.
25. Candidate age limits, gender, hometown exclusions, appearance and personality go only to manual_review.
26. Do not invent qualifications not stated.

RAW MIXED-PLATFORM EMPLOYER TEXT:
{raw_text}
"""


def normalize_raw_orders_with_gemini(raw_text: str) -> Tuple[List[Dict[str, Any]], str]:
    request_text = str(raw_text or "").strip()
    if not request_text:
        raise ValueError("请先粘贴雇主原始订单。")

    # One AI request handles the entire normalization stage.  Keep a practical
    # input guard so Community Cloud / free-tier output is less likely to truncate.
    if len(request_text) > 50000:
        raise ValueError("本次原始订单文字过长。建议分成两批，每批不超过约 5 万字符。")

    prompt = build_order_standardizer_prompt(request_text)
    payload, model_used = generate_json_prompt(prompt)
    raw_orders = payload.get("orders", [])

    if not isinstance(raw_orders, list) or not raw_orders:
        raise RuntimeError("Gemini 没有返回可识别的标准订单列表。")
    if len(raw_orders) > 60:
        raise RuntimeError("Gemini 一次识别出超过 60 条订单。为避免异常合并，请分批处理。")

    parsed_orders: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_orders, start=1):
        if not isinstance(raw, dict):
            raise RuntimeError(f"第 {index} 条标准化结果不是 JSON object。")

        # Do not source-ground against the entire mixed source text.  The whole
        # purpose of V1.7 is to make the AI-normalized order the authoritative
        # boundary, then let a human review/edit it before matching.
        parsed = normalize_parsed_order_from_raw(
            raw=raw,
            original_request="",
            model_used=model_used,
        )
        parsed["original_request"] = str(raw.get("source_excerpt") or "").strip()
        parsed["source_excerpt"] = str(raw.get("source_excerpt") or "").strip()
        parsed_orders.append(parsed)

    return parsed_orders, model_used


def canonical_order_payload(parsed: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Minimal canonical payload used in the human-editable standard-order box."""
    return {
        "Standard Index": index,
        "source_excerpt": parsed.get("source_excerpt") or parsed.get("original_request") or "",
        "order_info": parsed.get("order_info", {}),
        "hard_requirements": parsed.get("hard_requirements", {}),
        "preferred_requirements": parsed.get("preferred_requirements", {}),
        "reference_requirements": parsed.get("reference_requirements", {}),
        "manual_review": parsed.get("manual_review", {}),
    }


def standardized_orders_to_text(parsed_orders: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for index, parsed in enumerate(parsed_orders, start=1):
        payload = canonical_order_payload(parsed, index)
        blocks.append(
            STANDARD_ORDER_START
            + "\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
            + "\n"
            + STANDARD_ORDER_END
        )
    return "\n\n".join(blocks)


def parse_standardized_orders_text(standard_text: str) -> List[Dict[str, Any]]:
    """Parse recruiter-reviewed canonical order text without any Gemini call."""
    text = str(standard_text or "").strip()
    if not text:
        raise ValueError("标准订单框为空。请先执行『AI统一订单格式』。")

    pattern = re.compile(
        re.escape(STANDARD_ORDER_START) + r"\s*(.*?)\s*" + re.escape(STANDARD_ORDER_END),
        flags=re.DOTALL,
    )
    block_texts = pattern.findall(text)

    # Friendly fallback: allow a recruiter to paste one top-level JSON object
    # with an orders array into the editor.
    if not block_texts:
        try:
            payload = json.loads(clean_json_text(text))
        except Exception as exc:
            raise ValueError(
                "没有找到标准订单边界。请保留 '===== ORDER START =====' 和 "
                "'===== ORDER END =====' 标记。"
            ) from exc
        if isinstance(payload, dict) and isinstance(payload.get("orders"), list):
            raw_orders = payload["orders"]
        elif isinstance(payload, list):
            raw_orders = payload
        elif isinstance(payload, dict) and "order_info" in payload:
            raw_orders = [payload]
        else:
            raise ValueError("标准订单 JSON 中没有可识别的 orders。")
    else:
        raw_orders = []
        for index, block in enumerate(block_texts, start=1):
            try:
                raw = json.loads(block.strip())
            except json.JSONDecodeError as exc:
                raise ValueError(f"第 {index} 个标准订单 JSON 被修改成了无效格式。") from exc
            raw_orders.append(raw)

    if not raw_orders:
        raise ValueError("没有可匹配的标准订单。")

    parsed_orders: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_orders, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 条标准订单不是 JSON object。")
        parsed = normalize_parsed_order_from_raw(
            raw=raw,
            original_request="",
            model_used="standardized-local",
        )
        source_excerpt = str(raw.get("source_excerpt") or "").strip()
        parsed["original_request"] = source_excerpt
        parsed["source_excerpt"] = source_excerpt
        parsed_orders.append(parsed)

    return parsed_orders


def standardized_preview_rows(parsed_orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, parsed in enumerate(parsed_orders, start=1):
        info = parsed.get("order_info", {})
        rows.append(
            {
                "序号": index,
                "订单编号": info.get("Order ID") or "未识别",
                "城市": format_list(info.get("Working Cities")),
                "岗位": info.get("Job Type") or "未识别",
                "孩子年龄": format_list(info.get("Child Ages")),
                "薪资": info.get("Salary Text") or "未填写",
                "硬条件数": len(parsed.get("hard_requirements", {})),
                "人工复核项": len(parsed.get("manual_review", {})),
            }
        )
    return rows


def standardization_quality_warnings(parsed_orders: List[Dict[str, Any]]) -> List[str]:
    warnings: List[str] = []
    for index, parsed in enumerate(parsed_orders, start=1):
        info = parsed.get("order_info", {})
        cities = normalize_multi_text(info.get("Working Cities"))
        if not cities:
            warnings.append(f"第 {index} 条订单没有识别出工作城市，请人工确认。")
        if not info.get("Job Type"):
            warnings.append(f"第 {index} 条订单没有识别出岗位名称，请人工确认。")
        if len(cities) >= 3:
            warnings.append(
                f"第 {index} 条订单同时包含 {len(cities)} 个城市（{', '.join(cities)}），"
                "请确认它确实是同一家庭的多城市岗位，而不是串单。"
            )
        salary = str(info.get("Salary Text") or "")
        if salary.count(";") + salary.count("；") >= 1:
            warnings.append(f"第 {index} 条订单薪资中包含多个片段，请确认是否来自同一订单。")
    return warnings


def normalize_to_editor_session(raw_text: str, editor_key: str, model_key: str) -> None:
    parsed_orders, model_used = normalize_raw_orders_with_gemini(raw_text)
    st.session_state[editor_key] = standardized_orders_to_text(parsed_orders)
    st.session_state[model_key] = model_used


def estimated_batch_calls(order_count: int) -> int:
    if order_count <= 0:
        return 0
    return math.ceil(order_count / BATCH_CHUNK_SIZE)


def parse_employer_orders_batch(batch_text: str) -> List[Dict[str, Any]]:
    """Parse many orders after deterministic Python splitting.

    Every Gemini chunk must return exactly one object for every source block.
    If the count/indexes do not match, the system stops instead of silently
    merging employer orders.
    """
    order_blocks = split_batch_orders(batch_text)
    if not order_blocks:
        raise ValueError("请先粘贴雇主订单。")
    if len(order_blocks) > 40:
        raise ValueError("一次最多建议解析 40 条订单，请分两批处理。")

    parsed_by_global_index: Dict[int, Dict[str, Any]] = {}

    for chunk_start in range(0, len(order_blocks), BATCH_CHUNK_SIZE):
        chunk_blocks = order_blocks[chunk_start : chunk_start + BATCH_CHUNK_SIZE]
        prompt = build_batch_parser_prompt(chunk_blocks)
        payload, model_used = generate_json_prompt(prompt)
        raw_orders = payload.get("orders", [])

        if not isinstance(raw_orders, list):
            raise RuntimeError("Gemini 批量返回的 orders 不是数组。")

        expected_count = len(chunk_blocks)
        if len(raw_orders) != expected_count:
            raise RuntimeError(
                f"为防止订单合并，本批次已停止：Python 拆出 {expected_count} 条，"
                f"但 Gemini 返回 {len(raw_orders)} 条。请直接重新运行本批次。"
            )

        local_map: Dict[int, Dict[str, Any]] = {}
        for fallback_local_index, raw in enumerate(raw_orders, start=1):
            if not isinstance(raw, dict):
                raise RuntimeError("Gemini 返回了非对象订单，已停止以避免错单。")

            source_index_number = to_number(raw.get("Source Index"))
            local_index = int(source_index_number) if source_index_number is not None else fallback_local_index

            if local_index < 1 or local_index > expected_count:
                raise RuntimeError(f"Gemini 返回了无效 Source Index: {local_index}。")
            if local_index in local_map:
                raise RuntimeError(f"Gemini 重复返回 Source Index {local_index}，已停止以避免合并订单。")
            local_map[local_index] = raw

        expected_indexes = set(range(1, expected_count + 1))
        if set(local_map) != expected_indexes:
            raise RuntimeError("Gemini 返回的 Source Index 不完整，已停止以避免订单错位。")

        for local_index in range(1, expected_count + 1):
            global_index = chunk_start + local_index
            parsed_by_global_index[global_index] = normalize_parsed_order_from_raw(
                raw=local_map[local_index],
                original_request=order_blocks[global_index - 1],
                model_used=model_used,
            )

    parsed_orders = [parsed_by_global_index[index] for index in range(1, len(order_blocks) + 1)]
    return parsed_orders


def order_title(parsed: Dict[str, Any], fallback_index: Optional[int] = None) -> str:
    info = parsed.get("order_info", {})
    order_id = str(info.get("Order ID") or "").strip()
    cities = format_list(info.get("Working Cities"))
    job_type = str(info.get("Job Type") or "").strip()
    parts = [x for x in [order_id, cities if cities != "未填写" else "", job_type] if x]
    if parts:
        return " · ".join(parts)
    if fallback_index is not None:
        return f"订单 {fallback_index}"
    return "未命名订单"


def status_text(status: str) -> str:
    if status == "confirmed":
        return "✅ 已确认匹配"
    if status == "pending":
        return "⚠️ 待确认"
    return "❌ 有冲突"


def run_batch_matching(
    teachers: List[Dict[str, Any]],
    parsed_orders: List[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    bundle: List[Dict[str, Any]] = []
    for parsed in parsed_orders:
        results = run_matching(teachers, parsed, top_n=top_k)
        bundle.append({"parsed": parsed, "results": results})
    return bundle


def match_teacher_to_orders(
    teacher: Dict[str, Any],
    parsed_orders: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for parsed in parsed_orders:
        result = match_teacher(teacher, parsed)
        rows.append({"parsed": parsed, "match": result})
    rows.sort(
        key=lambda item: (
            item["match"]["status_rank"],
            item["match"]["score"],
            item["match"]["confirmation"],
        ),
        reverse=True,
    )
    return rows


def compact_field_names(fields: List[str]) -> str:
    return "、".join(field_label(field) for field in fields) if fields else "无"


def render_compact_candidate(rank: int, item: Dict[str, Any]) -> None:
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.markdown(f"**{rank}. {item['name']}**")
            st.caption(status_text(item["status"]))
        with c2:
            st.metric("匹配度", f"{item['score']}%")
        with c3:
            st.metric("确认度", f"{item['confirmation']}%")

        if item["hard"][CONFLICT]:
            st.write("❌ **硬条件冲突：**", compact_field_names(item["hard"][CONFLICT]))
        if item["hard"][UNKNOWN]:
            st.write("⚠️ **待确认：**", compact_field_names(item["hard"][UNKNOWN]))
        if item["hard"][MATCH]:
            st.write("✅ **已匹配：**", compact_field_names(item["hard"][MATCH]))


def render_parsed_order_compact(parsed: Dict[str, Any]) -> None:
    left, right = st.columns([1, 2])
    with left:
        render_order_info(parsed.get("order_info", {}))
    with right:
        h, p, r = st.columns(3)
        with h:
            render_requirement_group("岗位硬条件", parsed.get("hard_requirements", {}))
        with p:
            render_requirement_group("偏好条件", parsed.get("preferred_requirements", {}))
        with r:
            render_requirement_group("参考条件", parsed.get("reference_requirements", {}))

    manual = parsed.get("manual_review", {})
    if manual:
        st.warning("以下内容只供人工复核，不参与自动匹配：")
        for key, value in manual.items():
            st.write(f"**{key}：** {requirement_value(value)}")


def batch_summary_rows(bundle: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, entry in enumerate(bundle, start=1):
        parsed = entry["parsed"]
        info = parsed.get("order_info", {})
        row: Dict[str, Any] = {
            "序号": index,
            "订单编号": info.get("Order ID") or "未识别",
            "城市": format_list(info.get("Working Cities")),
            "岗位": info.get("Job Type") or "未识别",
        }
        for candidate_index in range(top_k):
            if candidate_index < len(entry["results"]):
                item = entry["results"][candidate_index]
                row[f"Top {candidate_index + 1}"] = item["name"]
                row[f"Top {candidate_index + 1} 匹配度"] = f"{item['score']}%"
                row[f"Top {candidate_index + 1} 状态"] = status_text(item["status"])
            else:
                row[f"Top {candidate_index + 1}"] = ""
                row[f"Top {candidate_index + 1} 匹配度"] = ""
                row[f"Top {candidate_index + 1} 状态"] = ""
        rows.append(row)
    return rows


def reverse_summary_rows(reverse_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, entry in enumerate(reverse_results, start=1):
        parsed = entry["parsed"]
        result = entry["match"]
        info = parsed.get("order_info", {})
        rows.append(
            {
                "排名": index,
                "订单编号": info.get("Order ID") or "未识别",
                "城市": format_list(info.get("Working Cities")),
                "岗位": info.get("Job Type") or "未识别",
                "匹配度": f"{result['score']}%",
                "状态": status_text(result["status"]),
                "硬条件确认度": f"{result['confirmation']}%",
                "冲突": compact_field_names(result["hard"][CONFLICT]),
                "待确认": compact_field_names(result["hard"][UNKNOWN]),
            }
        )
    return rows


def render_api_error(exc: Exception) -> None:
    text = str(exc)
    lower = text.lower()
    if "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in lower or "rate limit" in lower:
        st.error("Gemini API 当前额度已达到限制。")
        st.warning("请等待额度恢复或调整 Gemini API 计费/额度后再次运行。Baserow 老师数据不受影响。")
    elif isinstance(exc, ValueError):
        st.warning(text)
    elif "json" in lower and ("gemini" in lower or "格式" in text or "不完整" in text):
        st.error("Gemini 返回的结构化结果不完整。")
        st.info("请重新运行一次。批量模式会自动分成小批次解析，避免一次返回太长导致 JSON 截断。")
    else:
        st.error("处理过程中发生错误。")
        st.exception(exc)


# ============================================================
# 9. VALIDATE CONFIG / LOAD DATA
# ============================================================

config_errors = []
if not BASEROW_TOKEN:
    config_errors.append("缺少 BASEROW_TOKEN")
if TABLE_ID is None:
    config_errors.append("缺少或无效的 TABLE_ID")
if not GEMINI_API_KEY:
    config_errors.append("缺少 GEMINI_API_KEY")

if config_errors:
    st.error("Secrets 配置不完整：")
    for error in config_errors:
        st.write(f"• {error}")
    st.stop()

try:
    teachers = load_teachers()
except Exception as exc:
    st.error("无法读取 Baserow 老师数据库。")
    st.exception(exc)
    st.stop()


# ============================================================
# 10. SIDEBAR
# ============================================================

with st.sidebar:
    st.title("🎓 Teacher Matching")
    st.caption("V1.7 · AI统一订单格式 / 人工确认 / 本地匹配")
    st.divider()
    st.markdown("### 系统状态")

    baserow_status = check_baserow_connection()
    if baserow_status["success"]:
        st.success("Baserow 已连接")
    else:
        st.error("Baserow 连接失败")
        st.caption(baserow_status["message"])

    gemini_status = check_gemini_config()
    if gemini_status["success"]:
        st.success("Gemini 已配置")
        st.caption(f"模型：{gemini_status['model']}")
    else:
        st.error("Gemini 未配置")
        st.caption(gemini_status["message"])

    st.divider()
    st.markdown("### 老师数据库")
    st.metric("老师总数", len(teachers))
    if st.button("刷新老师数据", use_container_width=True):
        load_teachers.clear()
        st.rerun()

    st.divider()
    st.info(
        "单个订单模式：1 次 Gemini 请求。\n\n"
        "批量模式：① Gemini 用 1 次请求把不同平台订单统一成标准格式；"
        "② 人工确认；③ Python 本地匹配，0 次额外 Gemini。\n\n"
        "老师反向匹配复用标准订单池：0 次新的 Gemini 请求。"
    )


# ============================================================
# 11. HEADER / MODE SELECTOR
# ============================================================

st.markdown('<div class="main-title">AI Teacher Matching System</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="main-subtitle">V1.7：不同平台原始订单 → AI统一标准格式 → 人工确认 → Python本地匹配。</div>',
    unsafe_allow_html=True,
)

mode = st.radio(
    "选择匹配模式",
    [
        "① 单个订单 → 匹配全部老师",
        "② 批量订单 → 每单推荐老师",
        "③ 选择老师 → 匹配全部订单",
    ],
    horizontal=True,
)


# ============================================================
# 12. MODE 1 - SINGLE ORDER
# ============================================================

if mode == "① 单个订单 → 匹配全部老师":
    st.markdown('<div class="section-title">单个订单匹配</div>', unsafe_allow_html=True)
    st.caption("粘贴 1 条订单。Gemini 解析 1 次，然后本地 Python 与 Baserow 中全部老师匹配。")

    example = (
        "订单编码：HXC20260806688 北京朝阳区（住家）儿陪师。"
        "内容：专带4岁女宝；宝宝已经上国际幼儿园；老师有独立房间，不用带睡。"
        "要求：40岁以内；英语好；本科及以上学历。"
    )

    single_request = st.text_area(
        "雇主需求",
        height=220,
        placeholder=example,
        key="single_request_text",
    )

    b1, b2 = st.columns([4, 1])
    with b1:
        single_start = st.button("开始单单匹配", type="primary", use_container_width=True)
    with b2:
        single_clear = st.button("清除单单结果", use_container_width=True)

    if single_clear:
        for key in ["single_parsed_order", "single_matching_results"]:
            st.session_state.pop(key, None)
        st.rerun()

    if single_start:
        request_text = single_request.strip()
        if not request_text:
            st.warning("请先粘贴一条雇主订单。")
        else:
            try:
                with st.spinner("Gemini 正在解析订单并匹配全部老师..."):
                    parsed = parse_employer_order(request_text)
                    results = run_matching(teachers, parsed, top_n=TOP_N)
                    st.session_state["single_parsed_order"] = parsed
                    st.session_state["single_matching_results"] = results
            except Exception as exc:
                render_api_error(exc)

    single_parsed = st.session_state.get("single_parsed_order")
    single_results = st.session_state.get("single_matching_results")

    if single_parsed:
        st.divider()
        st.markdown("### AI 解析后的订单")
        with st.expander("查看原始订单"):
            st.write(single_parsed["original_request"])
        render_parsed_order_compact(single_parsed)
        if single_parsed.get("warnings"):
            with st.expander("解析提示"):
                for warning in single_parsed["warnings"]:
                    st.warning(warning)

    if single_results is not None:
        st.divider()
        st.markdown("### 推荐老师")
        confirmed = sum(1 for item in single_results if item["status"] == "confirmed")
        pending = sum(1 for item in single_results if item["status"] == "pending")
        conflicts = sum(1 for item in single_results if item["status"] == "conflict")
        best = single_results[0]["score"] if single_results else 0

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("候选人数", len(single_results))
        with m2:
            st.metric("硬条件确认匹配", confirmed)
        with m3:
            st.metric("需要人工确认", pending)
        with m4:
            st.metric("最高匹配度", f"{best}%")
        if conflicts:
            st.caption(f"另外有 {conflicts} 位候选人存在已确认的岗位硬条件冲突。")

        for index, item in enumerate(single_results, start=1):
            render_teacher_card(index, item)


# ============================================================
# 13. MODE 2 - BATCH ORDERS
# ============================================================

elif mode == "② 批量订单 → 每单推荐老师":
    st.markdown('<div class="section-title">批量订单匹配</div>', unsafe_allow_html=True)
    st.caption(
        "V1.7 使用两阶段流程：先让 Gemini 把不同平台、不同排版的原始派单统一成标准订单格式；"
        "你确认/修改以后，再由 Python 本地读取标准订单并匹配全部老师。"
    )

    st.markdown("### 第一步：粘贴不同平台的原始雇主需求")
    batch_raw_text = st.text_area(
        "原始订单信息",
        height=420,
        placeholder=(
            "这里可以混合粘贴微信派单、家政平台、猎头信息、客户自己发的文字等。\n\n"
            "不要求统一格式。"
        ),
        key="batch_raw_request_text",
    )

    n1, n2 = st.columns([4, 1])
    with n1:
        batch_normalize = st.button(
            "① AI统一订单格式",
            type="primary",
            use_container_width=True,
            key="batch_normalize_button",
        )
    with n2:
        batch_clear = st.button("清除批量订单", use_container_width=True, key="batch_clear_button_v17")

    if batch_clear:
        for key in [
            "batch_raw_request_text",
            "batch_standard_editor",
            "batch_standard_model",
            "batch_parsed_orders",
            "batch_matching_bundle",
            "batch_top_k_saved",
        ]:
            st.session_state.pop(key, None)
        st.rerun()

    if batch_normalize:
        if not batch_raw_text.strip():
            st.warning("请先粘贴原始雇主订单。")
        else:
            try:
                with st.spinner("Gemini 正在识别不同平台订单，并统一成标准格式..."):
                    normalize_to_editor_session(
                        batch_raw_text,
                        editor_key="batch_standard_editor",
                        model_key="batch_standard_model",
                    )
                    # New normalization invalidates previous matching results.
                    for key in ["batch_parsed_orders", "batch_matching_bundle", "batch_top_k_saved"]:
                        st.session_state.pop(key, None)
                st.rerun()
            except Exception as exc:
                render_api_error(exc)

    if "batch_standard_editor" in st.session_state:
        st.divider()
        st.markdown("### 第二步：检查 AI 统一后的标准订单")
        st.info(
            "下面已经是系统的固定格式。你可以直接修改字段，但请保留每条订单外面的 "
            "`===== ORDER START =====` / `===== ORDER END =====` 标记。"
        )

        batch_standard_text = st.text_area(
            "标准化后的订单（可人工修改）",
            height=650,
            key="batch_standard_editor",
        )

        current_parsed_orders: List[Dict[str, Any]] = []
        standard_parse_ok = False
        try:
            current_parsed_orders = parse_standardized_orders_text(batch_standard_text)
            standard_parse_ok = True
        except Exception as exc:
            st.error(f"标准订单格式当前无法读取：{exc}")

        if standard_parse_ok:
            st.success(
                f"当前标准订单框中共有 **{len(current_parsed_orders)} 条独立订单**。"
                "此处只是 Python 本地读取，没有新增 Gemini 请求。"
            )
            st.dataframe(
                standardized_preview_rows(current_parsed_orders),
                use_container_width=True,
                hide_index=True,
            )

            quality_warnings = standardization_quality_warnings(current_parsed_orders)
            if quality_warnings:
                with st.expander("⚠️ AI标准化后建议人工检查的项目", expanded=True):
                    for warning in quality_warnings:
                        st.warning(warning)

            with st.expander("逐条查看标准订单"):
                for preview_index, parsed_preview in enumerate(current_parsed_orders, start=1):
                    st.markdown(f"**{preview_index}. {order_title(parsed_preview, preview_index)}**")
                    render_parsed_order_compact(parsed_preview)
                    if preview_index < len(current_parsed_orders):
                        st.divider()

            st.markdown("### 第三步：确认标准订单并开始匹配")
            k1, k2 = st.columns([1, 3])
            with k1:
                batch_top_k = st.selectbox(
                    "每单推荐人数",
                    [3, 5, 10],
                    index=0,
                    key="batch_top_k_v17",
                )
            with k2:
                st.caption(
                    "点击下面按钮以后不再调用 Gemini。每条标准订单直接与 Baserow 全部老师进行 Python 本地匹配。"
                )

            batch_match = st.button(
                "② 确认标准格式并开始批量匹配",
                type="primary",
                use_container_width=True,
                key="batch_match_standardized",
            )

            if batch_match:
                try:
                    # Parse the live editor one more time so manual changes are authoritative.
                    parsed_orders = parse_standardized_orders_text(batch_standard_text)
                    with st.spinner("正在用标准订单本地匹配全部老师..."):
                        bundle = run_batch_matching(teachers, parsed_orders, top_k=batch_top_k)
                    st.session_state["batch_parsed_orders"] = parsed_orders
                    st.session_state["batch_matching_bundle"] = bundle
                    st.session_state["batch_top_k_saved"] = batch_top_k
                except Exception as exc:
                    render_api_error(exc)

    batch_parsed_orders = st.session_state.get("batch_parsed_orders")
    batch_bundle = st.session_state.get("batch_matching_bundle")
    saved_top_k = int(st.session_state.get("batch_top_k_saved", 3))

    if batch_parsed_orders:
        st.divider()
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("标准订单池", len(batch_parsed_orders))
        with m2:
            st.metric("老师数据库", len(teachers))
        with m3:
            st.metric("匹配阶段 Gemini 请求", "0 次")
        st.caption("这批已确认标准订单会自动成为『老师反向匹配』的当前订单池。")

    if batch_bundle:
        st.markdown("### 批量推荐总览")
        st.dataframe(
            batch_summary_rows(batch_bundle, saved_top_k),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### 每条订单详细结果")
        for order_index, entry in enumerate(batch_bundle, start=1):
            parsed = entry["parsed"]
            results = entry["results"]
            label = order_title(parsed, order_index)
            best_text = f" · Top1 {results[0]['name']} {results[0]['score']}%" if results else ""
            with st.expander(f"{order_index}. {label}{best_text}"):
                render_parsed_order_compact(parsed)
                st.markdown("#### 推荐老师")
                for candidate_index, item in enumerate(results, start=1):
                    render_compact_candidate(candidate_index, item)
                if parsed.get("warnings"):
                    for warning in parsed["warnings"]:
                        st.warning(warning)


# ============================================================
# 14. MODE 3 - ONE TEACHER TO ALL ORDERS
# ============================================================

else:
    st.markdown('<div class="section-title">选择老师 → 反向匹配全部订单</div>', unsafe_allow_html=True)
    st.caption("适合新老师入库后直接查：当前标准订单池里，哪些订单最适合这位老师？")

    teacher_indexes = list(range(len(teachers)))
    selected_teacher_index = st.selectbox(
        "选择老师",
        teacher_indexes,
        format_func=lambda index: teacher_name(teachers[index]),
        key="reverse_teacher_select",
    ) if teacher_indexes else None

    recent_batch = st.session_state.get("batch_parsed_orders") or []
    use_recent = False

    if recent_batch:
        use_recent = st.checkbox(
            f"直接使用最近一次已确认的 {len(recent_batch)} 条标准订单（0 次 Gemini 请求）",
            value=True,
            key="reverse_use_recent_v17",
        )
        if use_recent:
            st.dataframe(
                standardized_preview_rows(recent_batch),
                use_container_width=True,
                hide_index=True,
            )

    if not recent_batch or not use_recent:
        st.markdown("### 如果不使用当前订单池，也可以在这里建立新的标准订单池")
        reverse_raw_text = st.text_area(
            "粘贴不同平台的原始订单",
            height=360,
            placeholder="格式可以混合；先由 Gemini 统一格式，再由你确认。",
            key="reverse_raw_request_text_v17",
        )

        r1, r2 = st.columns([4, 1])
        with r1:
            reverse_normalize = st.button(
                "① AI统一这些订单格式",
                type="primary",
                use_container_width=True,
                key="reverse_normalize_v17",
            )
        with r2:
            reverse_clear = st.button(
                "清除反向订单",
                use_container_width=True,
                key="reverse_clear_v17",
            )

        if reverse_clear:
            for key in [
                "reverse_raw_request_text_v17",
                "reverse_standard_editor",
                "reverse_standard_model",
                "reverse_results",
                "reverse_teacher_name",
                "reverse_parsed_orders",
            ]:
                st.session_state.pop(key, None)
            st.rerun()

        if reverse_normalize:
            if not reverse_raw_text.strip():
                st.warning("请先粘贴订单。")
            else:
                try:
                    with st.spinner("Gemini 正在把这些订单统一成标准格式..."):
                        normalize_to_editor_session(
                            reverse_raw_text,
                            editor_key="reverse_standard_editor",
                            model_key="reverse_standard_model",
                        )
                        for key in ["reverse_results", "reverse_teacher_name", "reverse_parsed_orders"]:
                            st.session_state.pop(key, None)
                    st.rerun()
                except Exception as exc:
                    render_api_error(exc)

        if "reverse_standard_editor" in st.session_state:
            st.markdown("### 检查标准订单")
            reverse_standard_text = st.text_area(
                "标准订单（可人工修改）",
                height=600,
                key="reverse_standard_editor",
            )
            try:
                reverse_preview_orders = parse_standardized_orders_text(reverse_standard_text)
                st.success(f"当前识别为 {len(reverse_preview_orders)} 条标准订单。")
                st.dataframe(
                    standardized_preview_rows(reverse_preview_orders),
                    use_container_width=True,
                    hide_index=True,
                )
                for warning in standardization_quality_warnings(reverse_preview_orders):
                    st.warning(warning)
            except Exception as exc:
                reverse_preview_orders = []
                st.error(f"标准订单格式当前无法读取：{exc}")
    else:
        reverse_preview_orders = recent_batch

    reverse_start = st.button(
        "② 为这位老师扫描标准订单",
        type="primary",
        use_container_width=True,
        key="reverse_start_v17",
    )

    if reverse_start:
        if selected_teacher_index is None:
            st.warning("老师数据库为空。")
        else:
            try:
                selected_teacher = teachers[selected_teacher_index]
                if use_recent:
                    parsed_orders = recent_batch
                else:
                    standard_text = st.session_state.get("reverse_standard_editor", "")
                    parsed_orders = parse_standardized_orders_text(standard_text) if standard_text else []

                if not parsed_orders:
                    st.warning("请先准备并确认标准订单。")
                else:
                    with st.spinner("正在为老师扫描全部标准订单..."):
                        reverse_results = match_teacher_to_orders(selected_teacher, parsed_orders)
                    st.session_state["reverse_results"] = reverse_results
                    st.session_state["reverse_teacher_name"] = teacher_name(selected_teacher)
                    st.session_state["reverse_parsed_orders"] = parsed_orders
            except Exception as exc:
                render_api_error(exc)

    reverse_results = st.session_state.get("reverse_results")
    reverse_teacher_name = st.session_state.get("reverse_teacher_name")

    if reverse_results is not None:
        st.divider()
        st.markdown(f"### {reverse_teacher_name} 的订单推荐")

        confirmed = sum(1 for entry in reverse_results if entry["match"]["status"] == "confirmed")
        pending = sum(1 for entry in reverse_results if entry["match"]["status"] == "pending")
        conflicts = sum(1 for entry in reverse_results if entry["match"]["status"] == "conflict")

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("扫描订单数", len(reverse_results))
        with m2:
            st.metric("确认匹配", confirmed)
        with m3:
            st.metric("待确认", pending)
        with m4:
            st.metric("有明确冲突", conflicts)

        st.dataframe(
            reverse_summary_rows(reverse_results),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### 逐单查看")
        for rank, entry in enumerate(reverse_results, start=1):
            parsed = entry["parsed"]
            item = entry["match"]
            title = order_title(parsed, rank)
            with st.expander(f"{rank}. {title} · {item['score']}% · {status_text(item['status'])}"):
                render_parsed_order_compact(parsed)
                render_compact_candidate(1, item)


# ============================================================
# 15. FOOTER
# ============================================================

st.divider()
st.caption(
    "Teacher Matching System V1.7 · AI统一订单格式、人工确认、标准订单池、单单/批量/老师反向匹配。"
    "自动评分只使用岗位相关资格、能力与工作条件；个人属性要求仅供人工复核。"
)
