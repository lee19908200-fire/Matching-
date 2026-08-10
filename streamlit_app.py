# ============================================================
# AI Teacher Matching System V1.3
# Single-file Streamlit app
#
# Goals
# - Parse one employer order with Gemini
# - Read teachers from Baserow
# - Match only job-relevant qualifications / work conditions
# - Keep candidate age, gender, nationality/hometown and appearance
#   requirements in a manual-review section; they do NOT affect
#   automatic ranking or eligibility.
# - Treat missing teacher data as "待确认", not as automatic failure.
# - Child age is a reference-fit signal only, not a hard rejection.
# ============================================================

from __future__ import annotations

import json
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
    page_title="AI Teacher Matching System V1.3",
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
10. 幼儿园工作经历 -> Kindergarten Experience=true.
11. ADHD / SEN child -> SEN / ADHD Experience=true.
12. 全科辅导 -> General Tutoring Experience=true.
13. 家校对接 / 家校沟通 -> Family-School Communication Required=true.
14. 开车接送 / 熟练驾驶 -> Driving Required=true; 接送孩子 -> School Pick-up Required=true when driving/pickup is part of the job.
15. 跟随老板出差 -> Willing to Travel=true.
16. 辅食 -> Baby Food Required=true. 做饭/家常菜 -> Cooking Required=true. 家务/收纳 -> Housekeeping Required=true.
17. 营养搭配 -> Nutrition Planning=true.
18. 星级酒店从业经验 -> Luxury Hotel Experience=true.
19. PET/KET/AP/SAT exam preparation: put exam names under Exam Preparation when the job asks for exam preparation.
20. IB/AP/IGCSE/A-Level familiarity -> Curriculum array.
21. "最好/优先/优先考虑/ideally/preferred" -> preferred_requirements.
    Explicit "要求/必须/需要/工作内容必须完成" -> hard_requirements.
22. "无需家务/不做家务" means Housekeeping Required=false or simply omit it; it must never reject a teacher.
23. Job title such as 育儿师/儿陪师/家庭教师/私人助理/高端家务师 goes to Job Type only.
24. Do not invent qualifications that are not stated.
25. If input includes candidate age limits, gender, hometown exclusions, appearance, personality or similar personal traits, preserve them only in manual_review.

EMPLOYER ORDER:
{employer_request}
"""


def clean_json_text(text: str) -> str:
    cleaned = str(text or "").replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    return match.group(0) if match else cleaned


def normalize_requirement_group(group: Any) -> Tuple[Dict[str, Any], List[str]]:
    if not isinstance(group, dict):
        return {}, ["Gemini 返回的 requirement group 不是 dictionary。"]

    normalized: Dict[str, Any] = {}
    warnings: List[str] = []

    bool_fields = {
        "Live-in Required", "Night Care Required", "Private Room Provided", "Driving Required",
        "Early Years Experience", "Montessori Experience", "International School Experience",
        "Kindergarten Experience", "High-end Family Experience", "Private Tutoring Experience",
        "SEN / ADHD Experience", "Willing to Travel", "Cooking Required", "Baby Food Required",
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
        raise RuntimeError(f"Gemini 返回内容不是有效 JSON：{response.text[:1200]}") from exc

    order_info = normalize_order_info(raw.get("order_info"))
    hard, w1 = normalize_requirement_group(raw.get("hard_requirements", {}))
    preferred, w2 = normalize_requirement_group(raw.get("preferred_requirements", {}))
    reference, w3 = normalize_reference_group(raw.get("reference_requirements", {}), order_info)
    manual_review = normalize_manual_review(raw.get("manual_review", {}))

    # Ensure location/live-in context becomes job-relevant matching data.
    if order_info.get("Working Cities") and "Working Cities" not in hard:
        hard["Working Cities"] = order_info["Working Cities"]
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


def match_boolean_teacher_field(teacher: Dict[str, Any], field: str, required: Any) -> str:
    required_state = boolish(required)
    if required_state is not True:
        # False generally means the service is not required; do not reject a teacher.
        return NOT_APPLICABLE
    actual = boolish(teacher.get(field))
    if actual is None:
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
        # Relocation orders such as Changsha -> Singapore require willingness for all listed cities.
        return MATCH if {normalize_text(x) for x in required}.issubset(norm_preferred) else CONFLICT

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
        # Useful fallbacks for existing databases.
        if field == "Early Years Experience" and teacher.get(teacher_field) in (None, ""):
            subjects = {normalize_text(x) for x in teacher_list(teacher, "Subjects")}
            if normalize_text("Early Years") in subjects:
                return MATCH
        if field == "Montessori Experience" and teacher.get(teacher_field) in (None, ""):
            curriculum = {normalize_text(x) for x in teacher_list(teacher, "Curriculum")}
            if normalize_text("Montessori") in curriculum:
                return MATCH
        if field == "General Tutoring Experience" and teacher.get(teacher_field) in (None, ""):
            # Private tutoring is relevant evidence of tutoring, but not automatically proof of every subject.
            fallback = boolish(teacher.get("Private Tutoring Experience"))
            if fallback is True:
                return MATCH
        return match_boolean_teacher_field(teacher, teacher_field, expected)

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


def ratio(group: Dict[str, List[str]]) -> Optional[float]:
    known = len(group[MATCH]) + len(group[CONFLICT])
    return (len(group[MATCH]) / known) if known else None


def calculate_score(hard: Dict[str, List[str]], preferred: Dict[str, List[str]], reference: Dict[str, List[str]]) -> int:
    weighted = []
    for group, weight in [(hard, HARD_WEIGHT), (preferred, PREFERRED_WEIGHT), (reference, REFERENCE_WEIGHT)]:
        r = ratio(group)
        if r is not None:
            weighted.append((r, weight))
    if not weighted:
        return 0
    total_weight = sum(weight for _, weight in weighted)
    score = round(sum(r * weight for r, weight in weighted) / total_weight * 100)
    if hard[CONFLICT]:
        score = min(score, 79)
    return score


def hard_status(hard: Dict[str, List[str]]) -> Tuple[str, int]:
    if hard[CONFLICT]:
        return "conflict", 0
    if hard[UNKNOWN]:
        return "pending", 1
    return "confirmed", 2


def hard_confirmation_rate(hard: Dict[str, List[str]]) -> int:
    total = len(hard[MATCH]) + len(hard[CONFLICT]) + len(hard[UNKNOWN])
    if total == 0:
        return 100
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
# 8. VALIDATE CONFIG / LOAD DATA
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
# 9. SIDEBAR
# ============================================================

with st.sidebar:
    st.title("🎓 Teacher Matching")
    st.caption("V1.3 · Baserow + Gemini + Streamlit")
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
        "自动排序只使用岗位相关能力、资历与工作条件。"
        "候选人年龄、性别、国籍/籍贯、外貌等只进入人工复核备注，不参与自动排名。"
    )


# ============================================================
# 10. HEADER + INPUT
# ============================================================

st.markdown('<div class="main-title">AI Teacher Matching System</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="main-subtitle">粘贴一条雇主订单 → Gemini 结构化 → Baserow 老师库自动匹配 → 人工确认待核项。</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section-title">1. 输入一条雇主订单</div>', unsafe_allow_html=True)

example = (
    "订单编码：HXC20260806688 北京朝阳区（住家）儿陪师。"
    "内容：专带4岁女宝；宝宝已经上国际幼儿园；老师有独立房间，不用带睡。"
    "要求：40岁以内；英语好；本科及以上学历。"
)

employer_request = st.text_area("雇主需求", height=220, placeholder=example)

b1, b2 = st.columns([4, 1])
with b1:
    start_matching = st.button("开始匹配", type="primary", use_container_width=True)
with b2:
    clear = st.button("清除结果", use_container_width=True)

if clear:
    for key in ["parsed_order", "matching_results"]:
        st.session_state.pop(key, None)
    st.rerun()


# ============================================================
# 11. RUN
# ============================================================

if start_matching:
    request_text = employer_request.strip()
    if not request_text:
        st.warning("请先粘贴一条雇主订单。")
    else:
        try:
            with st.spinner("Gemini 正在解析订单并匹配老师..."):
                parsed = parse_employer_order(request_text)
                results = run_matching(teachers, parsed, top_n=TOP_N)
                st.session_state["parsed_order"] = parsed
                st.session_state["matching_results"] = results
        except Exception as exc:
            text = str(exc)
            if "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower() or "rate limit" in text.lower():
                st.error("Gemini API 当前额度已达到限制。")
                st.warning("请等待额度恢复或调整 Gemini API 计费/额度后再次点击『开始匹配』。Baserow 数据不受影响。")
            else:
                st.error("匹配过程中发生错误。")
                st.exception(exc)


# ============================================================
# 12. PARSED ORDER
# ============================================================

parsed = st.session_state.get("parsed_order")
results = st.session_state.get("matching_results")

if parsed:
    st.divider()
    st.markdown('<div class="section-title">2. AI 解析后的订单</div>', unsafe_allow_html=True)

    with st.expander("查看原始订单"):
        st.write(parsed["original_request"])

    o1, o2 = st.columns([1, 2])
    with o1:
        render_order_info(parsed.get("order_info", {}))
    with o2:
        h, p, r = st.columns(3)
        with h:
            render_requirement_group("岗位硬条件", parsed.get("hard_requirements", {}))
        with p:
            render_requirement_group("偏好条件", parsed.get("preferred_requirements", {}))
        with r:
            render_requirement_group("参考条件", parsed.get("reference_requirements", {}))

    manual = parsed.get("manual_review", {})
    if manual:
        st.warning("以下内容仅供招聘人员人工复核，不参与自动筛选、匹配度或排序：")
        for key, value in manual.items():
            st.write(f"**{key}：** {requirement_value(value)}")

    if parsed.get("warnings"):
        with st.expander("解析提示"):
            for warning in parsed["warnings"]:
                st.warning(warning)

    with st.expander("查看 Gemini 原始 JSON"):
        st.json(parsed.get("raw_requirements", {}))


# ============================================================
# 13. RESULTS
# ============================================================

if results is not None:
    st.divider()
    st.markdown('<div class="section-title">3. 推荐老师</div>', unsafe_allow_html=True)

    confirmed = sum(1 for item in results if item["status"] == "confirmed")
    pending = sum(1 for item in results if item["status"] == "pending")
    conflicts = sum(1 for item in results if item["status"] == "conflict")
    best = results[0]["score"] if results else 0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("候选人数", len(results))
    with m2:
        st.metric("硬条件已确认匹配", confirmed)
    with m3:
        st.metric("需要人工确认", pending)
    with m4:
        st.metric("最高岗位匹配度", f"{best}%")

    if conflicts:
        st.caption(f"另外有 {conflicts} 位候选人存在已确认的岗位硬条件冲突。")

    for index, item in enumerate(results, start=1):
        render_teacher_card(index, item)


# ============================================================
# 14. FOOTER
# ============================================================

st.divider()
st.caption("Teacher Matching System V1.3 · 自动评分仅使用岗位相关资格、能力与工作条件；个人属性要求仅供人工复核。")
