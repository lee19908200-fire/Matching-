# ============================================================
# AI Teacher Matching System V2.2.5
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
# - Ordinary driving/pickup duty is counted once via Driving; explicit pickup experience is separate.
# - Classified experience years support teaching/training, nanny educator, and high-end family work.
# - Pending candidates with zero confirmed hard-condition evidence display “资料不足”, not 0%.
# ============================================================

from __future__ import annotations

import json
import math
import re
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import streamlit as st
from google import genai
from google.genai import types
PDF_EXPORT_AVAILABLE = True
PDF_EXPORT_IMPORT_ERROR = ""

try:
    from PIL import Image as PILImage, ImageOps
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        Image as RLImage,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except Exception as _pdf_import_error:
    PDF_EXPORT_AVAILABLE = False
    PDF_EXPORT_IMPORT_ERROR = str(_pdf_import_error)
    PILImage = None
    ImageOps = None
    colors = None
    TA_CENTER = None
    TA_LEFT = None
    A4 = None
    ParagraphStyle = None
    mm = None
    pdfmetrics = None
    UnicodeCIDFont = None
    ImageReader = None
    RLImage = None
    Paragraph = None
    SimpleDocTemplate = None
    Spacer = None
    Table = None
    TableStyle = None


# ============================================================
# 1. PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Teacher Matching System V2.2.5",
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
    "Minimum Years of Teaching / Training Experience",
    "Minimum Years of Nanny Educator Experience",
    "Minimum Years of High-end Family Experience",
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


@st.cache_data(ttl=300, show_spinner=False)
def load_baserow_fields() -> List[Dict[str, Any]]:
    """Read the current Teachers table schema.

    The schema is used by the teacher-intake workflow so the app only writes
    field names/types that actually exist in the user's Baserow table.
    """
    if not BASEROW_TOKEN:
        raise RuntimeError("BASEROW_TOKEN 未配置。")
    if TABLE_ID is None:
        raise RuntimeError("TABLE_ID 未配置或格式不正确。")

    url = f"{BASEROW_BASE_URL}/api/database/fields/table/{TABLE_ID}/"
    response = requests.get(
        url,
        headers={"Authorization": f"Token {BASEROW_TOKEN}"},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Baserow 字段读取失败 HTTP {response.status_code}: {response.text[:600]}"
        )

    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Baserow 字段接口返回格式异常。")
    return payload


def baserow_field_map() -> Dict[str, Dict[str, Any]]:
    return {
        str(field.get("name")): field
        for field in load_baserow_fields()
        if field.get("name")
    }


def baserow_patch_row(row_id: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    if not BASEROW_TOKEN or TABLE_ID is None:
        raise RuntimeError("Baserow 配置不完整。")
    if not row_id:
        raise RuntimeError("老师 Baserow row ID 不存在。")
    if not data:
        raise ValueError("没有需要保存的数据。")

    url = f"{BASEROW_BASE_URL}/api/database/rows/table/{TABLE_ID}/{row_id}/"
    response = requests.patch(
        url,
        headers={
            "Authorization": f"Token {BASEROW_TOKEN}",
            "Content-Type": "application/json",
        },
        params={"user_field_names": "true"},
        json=data,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            f"Baserow 更新失败 HTTP {response.status_code}: {response.text[:1000]}"
        )
    return response.json()


def baserow_create_row(data: Dict[str, Any]) -> Dict[str, Any]:
    if not BASEROW_TOKEN or TABLE_ID is None:
        raise RuntimeError("Baserow 配置不完整。")
    if not data:
        raise ValueError("没有可写入的老师数据。")

    url = f"{BASEROW_BASE_URL}/api/database/rows/table/{TABLE_ID}/"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Token {BASEROW_TOKEN}",
            "Content-Type": "application/json",
        },
        params={"user_field_names": "true"},
        json=data,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            f"Baserow 新增老师失败 HTTP {response.status_code}: {response.text[:1200]}"
        )
    return response.json()


def baserow_upload_file(
    file_bytes: bytes,
    filename: str,
    mime_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload one file to Baserow user-files and return the uploaded file object."""
    if not BASEROW_TOKEN:
        raise RuntimeError("BASEROW_TOKEN 未配置。")
    if not file_bytes:
        raise ValueError("上传文件为空。")

    url = f"{BASEROW_BASE_URL}/api/user-files/upload-file/"
    files = {
        "file": (
            filename or "teacher_photo.jpg",
            file_bytes,
            mime_type or "application/octet-stream",
        )
    }
    response = requests.post(
        url,
        headers={"Authorization": f"Token {BASEROW_TOKEN}"},
        files=files,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            f"Baserow 文件上传失败 HTTP {response.status_code}: {response.text[:1000]}"
        )
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("name"):
        raise RuntimeError("Baserow 文件上传成功，但没有返回可关联的文件 name。")
    return payload


def select_options_for_field(field_schema: Dict[str, Any]) -> List[str]:
    options = []
    for option in field_schema.get("select_options") or []:
        value = option.get("value") if isinstance(option, dict) else option
        if value not in (None, ""):
            options.append(str(value))
    return options


def normalize_date_for_baserow(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    text = str(value).strip()
    # Accept YYYY-MM-DD directly.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    # Common Chinese / dotted formats.
    match = re.search(
        r"(?P<y>\d{4})[./年-](?P<m>\d{1,2})[./月-](?P<d>\d{1,2})",
        text,
    )
    if match:
        y = int(match.group("y"))
        m = int(match.group("m"))
        d = int(match.group("d"))
        return f"{y:04d}-{m:02d}-{d:02d}"
    return None


def serialize_value_for_baserow(
    value: Any,
    field_schema: Dict[str, Any],
) -> Tuple[Any, Optional[str]]:
    """Convert Gemini/editor values to Baserow's expected field value shape.

    Returns (serialized_value, warning).  A value of None means skip the field
    unless the caller intentionally wants to clear it.
    """
    if value is None or value == "" or value == [] or value == {}:
        return None, None

    field_name = str(field_schema.get("name") or "")
    field_type = str(field_schema.get("type") or "")

    if field_type in {"text", "long_text", "email", "phone_number", "url"}:
        return str(value).strip(), None

    if field_type in {"number", "rating", "duration"}:
        number = to_number(value)
        if number is None:
            return None, f"{field_name} 无法转换为数字，已跳过。"
        return int(number) if float(number).is_integer() else float(number), None

    if field_type == "boolean":
        state = boolish(value)
        if state is None:
            return None, None
        return state, None

    if field_type == "date":
        normalized = normalize_date_for_baserow(value)
        if not normalized:
            return None, f"{field_name} 日期格式无法确认，已跳过。"
        return normalized, None

    if field_type == "single_select":
        options = select_options_for_field(field_schema)
        raw = value.get("value") if isinstance(value, dict) else value
        raw_text = str(raw).strip()
        for option in options:
            if normalize_text(option) == normalize_text(raw_text):
                return option, None
        return None, (
            f"{field_name} 的值「{raw_text}」不在 Baserow 已有选项中，"
            f"已跳过。可选：{', '.join(options[:20])}"
        )

    if field_type == "multiple_select":
        options = select_options_for_field(field_schema)
        requested = normalize_multi_text(value)
        accepted: List[str] = []
        rejected: List[str] = []
        for item in requested:
            matched = next(
                (opt for opt in options if normalize_text(opt) == normalize_text(item)),
                None,
            )
            if matched:
                accepted.append(matched)
            else:
                rejected.append(item)
        warning = None
        if rejected:
            warning = (
                f"{field_name} 中以下值不在 Baserow 已有选项中，已跳过："
                + ", ".join(rejected)
            )
        return dedupe(accepted), warning

    # File fields are handled by the dedicated uploader.
    if field_type == "file":
        return None, None

    # Formula, lookup, link-row and other special fields should not be guessed.
    return None, f"{field_name} ({field_type}) 不属于自动写入字段类型，已跳过。"


def editable_teacher_schema_for_prompt() -> List[Dict[str, Any]]:
    """Build a compact schema for Gemini teacher-resume parsing."""
    result: List[Dict[str, Any]] = []
    supported_types = {
        "text", "long_text", "number", "boolean", "date",
        "single_select", "multiple_select", "email",
        "phone_number", "url",
    }

    for field in load_baserow_fields():
        field_type = str(field.get("type") or "")
        name = str(field.get("name") or "").strip()
        if not name or field_type not in supported_types:
            continue

        # These are inserted by the application from source-of-truth data,
        # not generated by Gemini.
        if name in {"Original Resume", "Teacher Photo"}:
            continue

        item: Dict[str, Any] = {
            "name": name,
            "type": field_type,
        }
        options = select_options_for_field(field)
        if options:
            item["allowed_values"] = options
        if field.get("primary"):
            item["primary"] = True
        result.append(item)

    return result[:100]


def build_teacher_resume_parser_prompt(original_resume: str) -> str:
    schema = editable_teacher_schema_for_prompt()
    resume_text = str(original_resume or "").strip()[:35000]

    return f"""
You are parsing ONE teacher/caregiver/private-family professional resume into
the user's existing Baserow Teachers table.

Return JSON only. No markdown fences.

STRICT FACTUALITY:
- Use only facts explicitly supported by the resume.
- Do not invent nationality, age, dates, certificates, curriculum knowledge,
  SEN/ADHD experience, night-care willingness, driving, visa/work authorization,
  cities, child-age range, or years of experience.
- You may calculate a duration only when the resume gives sufficiently clear dates.
  Do not double-count overlapping jobs.
- Do not create Latin/English names if the resume only provides a Chinese name.
- "Has a visa" is NOT "has work authorization".
- Serving a child enrolled in an international school is NOT the same as having
  worked as an international-school teacher.
- If a fact is unknown, return null (or [] for list fields).
- For select fields, use ONLY one of the provided allowed_values.
- Do not output fields that are not in BASEROW_FIELDS.

RETURN:
{{
  "teacher_data": {{
    "Exact Baserow Field Name": "value"
  }},
  "parse_notes": ["important ambiguities or items to confirm"],
  "source_evidence": {{
    "Exact Baserow Field Name": "short supporting resume excerpt/paraphrase"
  }}
}}

BASEROW_FIELDS:
{json.dumps(schema, ensure_ascii=False, indent=2)}

ORIGINAL RESUME:
{resume_text}
"""


def parse_teacher_resume(original_resume: str) -> Tuple[Dict[str, Any], str]:
    if not str(original_resume or "").strip():
        raise ValueError("请先粘贴老师完整原始简历。")

    prompt = build_teacher_resume_parser_prompt(original_resume)
    payload, model_used = generate_json_prompt(prompt)

    if not isinstance(payload, dict):
        raise RuntimeError("Gemini 老师简历解析返回格式异常。")

    teacher_data = payload.get("teacher_data")
    if not isinstance(teacher_data, dict):
        raise RuntimeError("Gemini 没有返回 teacher_data JSON object。")

    field_names = {str(field.get("name")) for field in load_baserow_fields()}
    cleaned = {
        str(key): value
        for key, value in teacher_data.items()
        if str(key) in field_names
    }

    return {
        "teacher_data": cleaned,
        "parse_notes": payload.get("parse_notes") if isinstance(payload.get("parse_notes"), list) else [],
        "source_evidence": payload.get("source_evidence") if isinstance(payload.get("source_evidence"), dict) else {},
    }, model_used


def prepare_teacher_row_for_baserow(
    teacher_data: Dict[str, Any],
    original_resume: str,
) -> Tuple[Dict[str, Any], List[str]]:
    """Validate editable JSON against the live Baserow table schema."""
    schema_map = baserow_field_map()
    payload: Dict[str, Any] = {}
    warnings: List[str] = []

    for field_name, value in (teacher_data or {}).items():
        schema = schema_map.get(str(field_name))
        if not schema:
            warnings.append(f"字段 {field_name} 当前不存在于 Baserow，已跳过。")
            continue

        serialized, warning = serialize_value_for_baserow(value, schema)
        if warning:
            warnings.append(warning)
        if serialized is not None:
            payload[str(field_name)] = serialized

    # Preserve the exact source resume, not Gemini's rewrite.
    if "Original Resume" in schema_map:
        payload["Original Resume"] = str(original_resume or "").strip()
    else:
        warnings.append(
            "Baserow 尚无 Original Resume 字段；本次可保存结构化数据，"
            "但完整原始简历不会永久入库。"
        )

    # Populate a blank text primary field from a sensible teacher name if needed.
    primary_fields = [
        f for f in schema_map.values()
        if f.get("primary") and f.get("type") in {"text", "long_text"}
    ]
    for primary in primary_fields:
        primary_name = str(primary.get("name"))
        if payload.get(primary_name):
            continue

        first = str(payload.get("First Name") or "").strip()
        last = str(payload.get("Last Name") or "").strip()
        chinese = str(payload.get("Chinese Name") or "").strip()
        candidate_name = " ".join(x for x in [first, last] if x).strip() or chinese
        if candidate_name:
            payload[primary_name] = candidate_name

    return payload, warnings


def teacher_photo_file(teacher: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for field_name in ["Teacher Photo", "Profile Photo", "Photo", "Image"]:
        value = teacher.get(field_name)
        for item in ensure_list(value):
            if isinstance(item, dict) and (item.get("url") or item.get("name")):
                return item
    return None


def teacher_photo_url(teacher: Dict[str, Any]) -> Optional[str]:
    item = teacher_photo_file(teacher)
    if not item:
        return None
    # Prefer original file URL; fall back to the largest available thumbnail.
    if item.get("url"):
        return str(item["url"])
    thumbnails = item.get("thumbnails") or {}
    for key in ["large", "medium", "small", "tiny"]:
        thumb = thumbnails.get(key)
        if isinstance(thumb, dict) and thumb.get("url"):
            return str(thumb["url"])
    return None


@st.cache_data(ttl=300, show_spinner=False)
def download_binary_url(url: str) -> bytes:
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.content


def save_original_resume_for_teacher(
    teacher: Dict[str, Any],
    original_resume: str,
) -> Dict[str, Any]:
    schema_map = baserow_field_map()
    if "Original Resume" not in schema_map:
        raise RuntimeError(
            "Teachers 表还没有 Original Resume 字段。请先在 Baserow 新增 Long text 字段。"
        )
    row_id = teacher.get("Baserow ID")
    return baserow_patch_row(
        row_id,
        {"Original Resume": str(original_resume or "").strip()},
    )



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


def is_transient_gemini_error(exc: Exception) -> bool:
    text = str(exc)
    upper = text.upper()
    transient_markers = [
        "500",
        "503",
        "504",
        "INTERNAL",
        "UNAVAILABLE",
        "DEADLINE_EXCEEDED",
        "SERVERERROR",
        "TIMEOUT",
        "TIMED OUT",
    ]
    return any(marker in upper for marker in transient_markers)


def is_gemini_not_found_error(exc: Exception) -> bool:
    text = str(exc)
    lower = text.lower()
    return (
        "404" in text
        or "NOT_FOUND" in text
        or "not available" in lower
        or "model_not_found" in lower
    )


def generate_content_resilient(
    client: genai.Client,
    prompt: str,
    preferred_model: Optional[str] = None,
) -> Tuple[Any, str]:
    """
    Generate JSON with a conservative model fallback.

    The google-genai SDK already retries transient 429/5xx errors internally.
    This helper adds ONE model fallback only for persistent 5xx/model-unavailable
    failures, so a temporary problem with one model does not crash the Streamlit app.
    """
    preferred = str(preferred_model or GEMINI_MODEL).strip()
    attempted: List[str] = []
    first_error: Optional[Exception] = None

    def call(model_name: str):
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )

    candidates = [preferred]

    try:
        available = list_generate_models(client)
        flash_alternatives = [
            model
            for model in available
            if "flash" in model.lower() and model != preferred
        ]
        # Only one fallback model is attempted to control quota/cost.
        if flash_alternatives:
            candidates.append(flash_alternatives[0])
    except Exception:
        pass

    for model_name in dedupe(candidates):
        attempted.append(model_name)
        try:
            response = call(model_name)
            return response, model_name
        except Exception as exc:
            if first_error is None:
                first_error = exc

            # Do not silently hop models for quota/auth/client-data problems.
            # Only model-not-found or persistent server-side 5xx failures qualify.
            if not (
                is_gemini_not_found_error(exc)
                or is_transient_gemini_error(exc)
            ):
                raise

            # Continue only if there is another candidate.
            continue

    attempted_text = ", ".join(attempted) or preferred
    raise RuntimeError(
        "GEMINI_TEMPORARY_UNAVAILABLE: Gemini 服务端暂时无法完成请求。"
        f"已尝试模型：{attempted_text}。"
        "订单/Baserow 数据没有丢失，请稍后重试；"
        "如果目标订单已经在标准订单池中，请直接使用标准订单池，"
        "该步骤无需再次调用 Gemini。"
    ) from first_error


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
    "Special Needs": [],
    "Job Duties": []
  }},
  "hard_requirements": {{}},
  "preferred_requirements": {{}},
  "reference_requirements": {{}},
  "compound_requirements": [],
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
- Minimum Years of Teaching / Training Experience: number
- Minimum Years of Nanny Educator Experience: number
- Minimum Years of High-end Family Experience: number
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
11. 有真实上户经历 / 陪伴师经历 / 儿陪师经历 / 育儿师经历 -> Nanny Educator Experience=true. If the stated years specifically refer to 儿陪/陪伴师/育儿/教育管家, use Minimum Years of Nanny Educator Experience. If the text only says generic relevant experience years, use Minimum Years of Relevant Experience.
11A. 教培/教学/学校教学 X 年 -> Minimum Years of Teaching / Training Experience=X. 高端/高净值家庭 X 年 -> High-end Family Experience=true and Minimum Years of High-end Family Experience=X.
12. ADHD / SEN child, when the teacher is expected to support that need -> SEN / ADHD Experience=true.
13. 全科辅导 -> General Tutoring Experience=true.
14. 家校对接 / 家校沟通 -> Family-School Communication Required=true.
15. 开车接送 / 熟练驾驶 / 负责接送孩子 -> Driving Required=true. Ordinary pickup/dropoff DUTY must NOT also create School Pick-up Required. Only when the employer explicitly requires prior/professional pickup-driver experience (e.g. “有接送孩子经验/有司机经验/有接送工作经验”) set School Pick-up Required=true.
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
25. Extract concrete day-to-day duties stated by the employer into order_info["Job Duties"] as short factual phrases, e.g. 学习辅导, 家校沟通, 开车接送, 早教启蒙, 家庭事务统筹. Do not invent duties.
26. Do not invent qualifications that are not stated.
26. If input includes candidate age limits, gender, hometown exclusions, appearance, personality or similar personal traits, preserve them only in manual_review.

COMBINATION-LOGIC RULES:
- All ordinary fields inside hard_requirements are AND conditions by default.
- Use compound_requirements ONLY when the employer explicitly gives alternatives or grouped logic such as "A或B", "A或者B", "A/B满足其一", "二选一", "任一即可".
- One compound group has:
  {{
    "Label": "human-readable label",
    "Logic": "OR" or "AND",
    "Options": [
      {{
        "Label": "option label",
        "Requirements": {{
          "Allowed Field": value
        }}
      }}
    ]
  }}
- Multiple fields inside ONE Option are AND conditions.
- For an OR group, satisfying ANY one Option is enough.
- Do not duplicate a condition in both hard_requirements and compound_requirements.

IMPORTANT EXAMPLE:
"5年以上教培经验或3年以上儿陪经验"
must become:
"compound_requirements": [
  {{
    "Label": "教培/儿陪经验",
    "Logic": "OR",
    "Options": [
      {{
        "Label": "5年以上教培经验",
        "Requirements": {{
          "Minimum Years of Teaching / Training Experience": 5
        }}
      }},
      {{
        "Label": "3年以上儿陪经验",
        "Requirements": {{
          "Nanny Educator Experience": true,
          "Minimum Years of Nanny Educator Experience": 3
        }}
      }}
    ]
  }}
]

ANOTHER EXAMPLE:
"有幼儿园经验或早教机构经验"
must become one OR compound group with:
- Option 1: Kindergarten Experience=true
- Option 2: Early Years Experience=true

For ordinary "英语流利且熟练驾驶", put BOTH Teaching Languages=["English"] and Driving Required=true
in hard_requirements. That is already AND, so no compound group is needed.

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
        elif field in {
            "Minimum Years of Relevant Experience",
            "Minimum Years of Teaching / Training Experience",
            "Minimum Years of Nanny Educator Experience",
            "Minimum Years of High-end Family Experience",
        }:
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
        "Job Duties": normalize_multi_text(info.get("Job Duties")),
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


def normalize_compound_requirements(value: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Normalize explicit OR / AND requirement groups.

    Multiple fields inside one Option are AND conditions.
    One compound group counts as ONE hard condition in scoring.
    """
    warnings: List[str] = []
    normalized_groups: List[Dict[str, Any]] = []

    if value is None or value == [] or value == {} or value == "":
        return normalized_groups, warnings

    if isinstance(value, dict):
        raw_groups = [value]
    elif isinstance(value, list):
        raw_groups = value
    else:
        return [], ["compound_requirements 不是 list/dict，已忽略。"]

    for group_index, raw_group in enumerate(raw_groups, start=1):
        if not isinstance(raw_group, dict):
            warnings.append(f"第 {group_index} 个组合条件不是 JSON object，已忽略。")
            continue

        label = str(
            raw_group.get("Label")
            or raw_group.get("label")
            or f"组合条件 {group_index}"
        ).strip()

        logic = str(
            raw_group.get("Logic")
            or raw_group.get("logic")
            or "OR"
        ).strip().upper()

        if logic not in {"OR", "AND"}:
            warnings.append(f"组合条件「{label}」Logic={logic} 无法识别，已按 OR 处理。")
            logic = "OR"

        raw_options = raw_group.get("Options")
        if raw_options is None:
            raw_options = raw_group.get("options")

        if not isinstance(raw_options, list) or not raw_options:
            warnings.append(f"组合条件「{label}」没有有效 Options，已忽略。")
            continue

        options: List[Dict[str, Any]] = []

        for option_index, raw_option in enumerate(raw_options, start=1):
            if not isinstance(raw_option, dict):
                warnings.append(f"组合条件「{label}」第 {option_index} 个 Option 不是 JSON object，已忽略。")
                continue

            option_label = str(
                raw_option.get("Label")
                or raw_option.get("label")
                or f"选项 {option_index}"
            ).strip()

            requirements_raw = raw_option.get("Requirements")
            if requirements_raw is None:
                requirements_raw = raw_option.get("requirements")

            if requirements_raw is None:
                requirements_raw = {
                    key: val
                    for key, val in raw_option.items()
                    if key not in {"Label", "label", "Requirements", "requirements"}
                }

            requirements, option_warnings = normalize_requirement_group(
                requirements_raw if isinstance(requirements_raw, dict) else {}
            )
            warnings.extend([f"组合条件「{label}」/「{option_label}」：{item}" for item in option_warnings])

            if not requirements:
                warnings.append(f"组合条件「{label}」选项「{option_label}」没有可匹配条件，已忽略。")
                continue

            options.append({"Label": option_label, "Requirements": requirements})

        if not options:
            warnings.append(f"组合条件「{label}」没有有效选项，已忽略。")
            continue

        normalized_groups.append({"Label": label, "Logic": logic, "Options": options})

    return normalized_groups, warnings


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
    response, model_used = generate_content_resilient(
        client,
        prompt,
        preferred_model=GEMINI_MODEL,
    )

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
    compound_requirements, w4 = normalize_compound_requirements(raw.get("compound_requirements", []))

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
        "compound_requirements": compound_requirements,
        "manual_review": manual_review,
        "raw_requirements": raw,
        "warnings": w1 + w2 + w3 + w4,
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
    "Minimum Years of Teaching / Training Experience": "最低教培/教学经验年限",
    "Minimum Years of Nanny Educator Experience": "最低儿陪/教育管家经验年限",
    "Minimum Years of High-end Family Experience": "最低高端家庭经验年限",
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
    "School Pick-up Required": "接送工作经验",
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
    "School Pick-up Required": "School Pick-up Experience",
    "Family-School Communication Required": "Family-School Communication",
    "General Tutoring Experience": "General Tutoring Experience",
    "Child Psychology Experience": "Child Psychology Experience",
    "Luxury Hotel Experience": "Luxury Hotel Experience",
    "Nutrition Planning": "Nutrition Planning",
}


COMPOUND_FIELD_PREFIX = "组合条件::"


def field_label(field: str) -> str:
    if str(field).startswith(COMPOUND_FIELD_PREFIX):
        return str(field)[len(COMPOUND_FIELD_PREFIX):]
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


def teacher_years_from_fields(teacher: Dict[str, Any], fields: Iterable[str]) -> Optional[float]:
    """Return the first explicit numeric experience-year value found in Baserow."""
    for candidate_field in fields:
        actual = to_number(teacher.get(candidate_field))
        if actual is not None:
            return actual
    return None


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
        actual = teacher_years_from_fields(
            teacher,
            ["Relevant Experience Years", "Years of Relevant Experience", "Years of Teaching"],
        )
        if required is None:
            return NOT_APPLICABLE
        if actual is None:
            return UNKNOWN
        return MATCH if actual >= required else CONFLICT

    if field == "Minimum Years of Teaching / Training Experience":
        required = to_number(expected)
        actual = teacher_years_from_fields(
            teacher,
            [
                "Teaching / Training Experience Years",
                "Teaching Experience Years",
                "Training Experience Years",
                "Years of Teaching",
            ],
        )
        if required is None:
            return NOT_APPLICABLE
        if actual is None:
            return UNKNOWN
        return MATCH if actual >= required else CONFLICT

    if field == "Minimum Years of Nanny Educator Experience":
        required = to_number(expected)
        if required is None:
            return NOT_APPLICABLE

        actual = teacher_years_from_fields(
            teacher,
            [
                "Nanny Educator Experience Years",
                "Nanny Educator Years",
                "Years of Nanny Educator Experience",
                "Years of Nanny Educator",
            ],
        )
        if actual is not None:
            return MATCH if actual >= required else CONFLICT

        # We know the teacher has this type of experience, but without a separate
        # numeric field we cannot safely invent the number of years.
        nanny_state = boolish(teacher.get("Nanny Educator Experience"))
        if nanny_state is True or evidence_keyword_match(
            teacher,
            ["教育管家", "儿陪师", "陪伴师", "育儿师", "育婴师", "nanny educator"],
        ):
            return UNKNOWN
        return UNKNOWN

    if field == "Minimum Years of High-end Family Experience":
        required = to_number(expected)
        if required is None:
            return NOT_APPLICABLE

        actual = teacher_years_from_fields(
            teacher,
            [
                "High-end Family Experience Years",
                "High-end Family Years",
                "Years of High-end Family Experience",
            ],
        )
        if actual is not None:
            return MATCH if actual >= required else CONFLICT

        high_end_state = boolish(teacher.get("High-end Family Experience"))
        if high_end_state is True or evidence_keyword_match(
            teacher,
            ["高净值家庭", "高端家庭", "private family"],
        ):
            return UNKNOWN
        return UNKNOWN

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


def merge_outcome_groups(
    target: Dict[str, List[str]],
    source: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    for bucket in [MATCH, CONFLICT, UNKNOWN, NOT_APPLICABLE]:
        for field in source.get(bucket, []):
            if field not in target[bucket]:
                target[bucket].append(field)
    return target


def option_outcome(teacher: Dict[str, Any], requirements: Dict[str, Any]) -> str:
    evaluated = evaluate_group(teacher, requirements)
    if evaluated[CONFLICT]:
        return CONFLICT
    if evaluated[UNKNOWN]:
        return UNKNOWN
    if evaluated[MATCH]:
        return MATCH
    return NOT_APPLICABLE


def evaluate_compound_requirements(
    teacher: Dict[str, Any],
    groups: Any,
) -> Tuple[Dict[str, List[str]], List[Dict[str, Any]]]:
    """Evaluate explicit OR/AND groups as one hard condition per group."""
    result = {MATCH: [], CONFLICT: [], UNKNOWN: [], NOT_APPLICABLE: []}
    details: List[Dict[str, Any]] = []
    normalized_groups, _warnings = normalize_compound_requirements(groups)

    for index, group in enumerate(normalized_groups, start=1):
        label = str(group.get("Label") or f"组合条件 {index}").strip()
        logic = str(group.get("Logic") or "OR").upper()
        options = group.get("Options", [])

        option_results: List[Dict[str, Any]] = []
        outcomes: List[str] = []

        for option in options:
            requirements = option.get("Requirements", {})
            outcome = option_outcome(teacher, requirements)
            outcomes.append(outcome)
            option_results.append({
                "Label": option.get("Label") or "选项",
                "Outcome": outcome,
                "Requirements": requirements,
            })

        usable = [value for value in outcomes if value != NOT_APPLICABLE]

        if not usable:
            group_outcome = NOT_APPLICABLE
        elif logic == "AND":
            if CONFLICT in usable:
                group_outcome = CONFLICT
            elif UNKNOWN in usable:
                group_outcome = UNKNOWN
            elif all(value == MATCH for value in usable):
                group_outcome = MATCH
            else:
                group_outcome = UNKNOWN
        else:
            if MATCH in usable:
                group_outcome = MATCH
            elif UNKNOWN in usable:
                group_outcome = UNKNOWN
            elif all(value == CONFLICT for value in usable):
                group_outcome = CONFLICT
            else:
                group_outcome = UNKNOWN

        synthetic_field = COMPOUND_FIELD_PREFIX + label
        result[group_outcome].append(synthetic_field)
        details.append({
            "Label": label,
            "Logic": logic,
            "Outcome": group_outcome,
            "Options": option_results,
        })

    return result, details


def match_teacher(
    teacher: Dict[str, Any],
    parsed: Dict[str, Any],
) -> Dict[str, Any]:
    hard = evaluate_group(teacher, parsed.get("hard_requirements", {}))
    compound_hard, compound_details = evaluate_compound_requirements(
        teacher, parsed.get("compound_requirements", [])
    )
    hard = merge_outcome_groups(hard, compound_hard)

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
        "compound_details": compound_details,
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


def render_compound_requirements(groups: Any) -> None:
    normalized_groups, warnings = normalize_compound_requirements(groups)
    st.markdown("#### 组合条件（OR / AND）")
    if not normalized_groups:
        st.caption("无")
        return

    for group_index, group in enumerate(normalized_groups, start=1):
        label = group.get("Label") or f"组合条件 {group_index}"
        logic = group.get("Logic") or "OR"
        st.write(f"**{label}｜{logic}**")
        for option_index, option in enumerate(group.get("Options", []), start=1):
            option_label = option.get("Label") or f"选项 {option_index}"
            reqs = option.get("Requirements", {})
            parts = [
                f"{field_label(field)}={requirement_value(value)}"
                for field, value in reqs.items()
            ]
            st.write(f"• {option_label}: " + (" + ".join(parts) if parts else "无可匹配字段"))

    for warning in warnings:
        st.warning(warning)


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
        "主要工作内容": format_list(info.get("Job Duties")),
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
            st.metric("岗位匹配度", score_text(item))
            st.caption(f"硬条件资料确认度：{item['confirmation']}%")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**年龄（仅展示，不参与自动排名）：**", format_number(teacher.get("Age")))
            st.write("**国籍（仅展示，不参与自动排名）：**", teacher.get("Nationality") or "未填写")
            current = ", ".join(str(x) for x in [teacher.get("Current City"), teacher.get("Current Country")] if x)
            st.write("**当前所在地：**", current or "未填写")
            st.write("**最高学历：**", teacher.get("Highest Degree") or "未填写")
            st.write("**相关经验年限：**", format_number(teacher.get("Years of Teaching")))
            teaching_years = teacher_years_from_fields(
                teacher,
                ["Teaching / Training Experience Years", "Teaching Experience Years", "Years of Teaching"],
            )
            nanny_years = teacher_years_from_fields(
                teacher,
                ["Nanny Educator Experience Years", "Nanny Educator Years", "Years of Nanny Educator Experience"],
            )
            high_end_years = teacher_years_from_fields(
                teacher,
                ["High-end Family Experience Years", "High-end Family Years", "Years of High-end Family Experience"],
            )
            if teaching_years is not None:
                st.write("**教培/教学经验年限：**", format_number(teaching_years))
            if nanny_years is not None:
                st.write("**儿陪/教育管家经验年限：**", format_number(nanny_years))
            if high_end_years is not None:
                st.write("**高端家庭经验年限：**", format_number(high_end_years))
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
        "Special Needs": [],
        "Job Duties": []
      }},
      "hard_requirements": {{}},
      "preferred_requirements": {{}},
      "reference_requirements": {{}},
      "compound_requirements": [],
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
- Minimum Years of Teaching / Training Experience: number
- Minimum Years of Nanny Educator Experience: number
- Minimum Years of High-end Family Experience: number
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
11. 有真实上户经历 / 陪伴师经历 / 儿陪师经历 / 育儿师经历 -> Nanny Educator Experience=true. If the stated years specifically refer to 儿陪/陪伴师/育儿/教育管家, use Minimum Years of Nanny Educator Experience. If the text only says generic relevant experience years, use Minimum Years of Relevant Experience.
11A. 教培/教学/学校教学 X 年 -> Minimum Years of Teaching / Training Experience=X. 高端/高净值家庭 X 年 -> High-end Family Experience=true and Minimum Years of High-end Family Experience=X.
12. ADHD / SEN child, when the teacher is expected to support that need -> SEN / ADHD Experience=true.
13. 全科辅导 -> General Tutoring Experience=true.
14. 家校对接 / 家校沟通 -> Family-School Communication Required=true.
15. 开车接送 / 熟练驾驶 / 负责接送孩子 -> Driving Required=true. Ordinary pickup/dropoff DUTY must NOT also create School Pick-up Required. Only an explicit prior/professional pickup-driver experience requirement creates School Pick-up Required=true.
16. 跟随老板出差 -> Willing to Travel=true.
17. 辅食 -> Baby Food Required=true. 做饭/家常菜 -> Cooking Required=true. 家务/收纳 -> Housekeeping Required=true.
18. 营养搭配 -> Nutrition Planning=true.
19. 星级酒店从业经验 -> Luxury Hotel Experience=true.
20. PET/KET/AP/SAT exam preparation -> Exam Preparation.
21. IB/AP/IGCSE/A-Level familiarity -> Curriculum.
22. "最好/优先/优先考虑" -> preferred_requirements. Explicit "要求/必须/需要" -> hard_requirements.
23. "无需家务/不做家务" may be Housekeeping Required=false or omitted, and must never reject a teacher.
24. Job title such as 育儿师/儿陪师/家庭教师/私人助理/高端家务师 goes to Job Type only.
25. Extract concrete day-to-day duties into order_info["Job Duties"] as short factual phrases. Do not invent duties.
26. Do not invent qualifications not stated.
26. Candidate age limits, gender, hometown exclusions, appearance, personality, and similar personal traits go only to manual_review.

COMBINATION-LOGIC RULES:
- All ordinary fields inside hard_requirements are AND conditions by default.
- Use compound_requirements ONLY when the employer explicitly gives alternatives or grouped logic such as "A或B", "A或者B", "A/B满足其一", "二选一", "任一即可".
- One compound group has:
  {{
    "Label": "human-readable label",
    "Logic": "OR" or "AND",
    "Options": [
      {{
        "Label": "option label",
        "Requirements": {{
          "Allowed Field": value
        }}
      }}
    ]
  }}
- Multiple fields inside ONE Option are AND conditions.
- For an OR group, satisfying ANY one Option is enough.
- Do not duplicate a condition in both hard_requirements and compound_requirements.

IMPORTANT EXAMPLE:
"5年以上教培经验或3年以上儿陪经验"
must become:
"compound_requirements": [
  {{
    "Label": "教培/儿陪经验",
    "Logic": "OR",
    "Options": [
      {{
        "Label": "5年以上教培经验",
        "Requirements": {{
          "Minimum Years of Teaching / Training Experience": 5
        }}
      }},
      {{
        "Label": "3年以上儿陪经验",
        "Requirements": {{
          "Nanny Educator Experience": true,
          "Minimum Years of Nanny Educator Experience": 3
        }}
      }}
    ]
  }}
]

ANOTHER EXAMPLE:
"有幼儿园经验或早教机构经验"
must become one OR compound group with:
- Option 1: Kindergarten Experience=true
- Option 2: Early Years Experience=true

For ordinary "英语流利且熟练驾驶", put BOTH Teaching Languages=["English"] and Driving Required=true
in hard_requirements. That is already AND, so no compound group is needed.

SOURCE ORDERS:
{numbered_orders}
"""


def generate_json_prompt(prompt: str) -> Tuple[Dict[str, Any], str]:
    """Run one Gemini JSON generation call with model fallback.

    Batch mode accepts both the requested ``{"orders": [...]}`` wrapper and a
    bare top-level array, because Gemini may occasionally omit the wrapper.
    """
    client = gemini_client()
    response, model_used = generate_content_resilient(
        client,
        prompt,
        preferred_model=GEMINI_MODEL,
    )

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
    compound_requirements, w4 = normalize_compound_requirements(raw.get("compound_requirements", []))

    # Source-grounding: identifiers, cities, district, job type, and child ages
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
        "compound_requirements": compound_requirements,
        "manual_review": manual_review,
        "raw_requirements": raw,
        "warnings": w1 + w2 + w3 + w4,
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
        "Special Needs": [],
        "Job Duties": []
      }},
      "hard_requirements": {{}},
      "preferred_requirements": {{}},
      "reference_requirements": {{}},
      "compound_requirements": [],
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
- Minimum Years of Teaching / Training Experience: number
- Minimum Years of Nanny Educator Experience: number
- Minimum Years of High-end Family Experience: number
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
11. 真实上户/陪伴师/儿陪师/育儿师/教育管家经历 -> Nanny Educator Experience=true. Years explicitly tied to this work -> Minimum Years of Nanny Educator Experience; generic relevant years -> Minimum Years of Relevant Experience.
11A. 教培/教学/学校教学 X 年 -> Minimum Years of Teaching / Training Experience=X. 高端/高净值家庭 X 年 -> High-end Family Experience=true and Minimum Years of High-end Family Experience=X.
12. ADHD / SEN child requiring support -> SEN / ADHD Experience=true.
13. 全科辅导 -> General Tutoring Experience=true.
14. 家校对接 / 家校沟通 -> Family-School Communication Required=true.
15. 熟练驾驶 / 开车接送 / 接送孩子作为工作内容 -> Driving Required=true. Do NOT duplicate ordinary pickup duty as School Pick-up Required. Set School Pick-up Required=true only when prior/professional pickup-driver experience is explicitly required.
16. 跟随老板出差 -> Willing to Travel=true.
17. 辅食 -> Baby Food Required=true; 做饭/家常菜 -> Cooking Required=true; 家务/收纳 -> Housekeeping Required=true.
18. 营养搭配 -> Nutrition Planning=true.
19. 星级酒店从业经验 -> Luxury Hotel Experience=true.
20. PET/KET/AP/SAT exam preparation -> Exam Preparation.
21. IB/AP/IGCSE/A-Level familiarity -> Curriculum.
22. "最好/优先/优先考虑" -> preferred_requirements; explicit "要求/必须/需要" -> hard_requirements.
23. "无需家务/不做家务" may be Housekeeping Required=false or omitted; it must never reject a teacher.
24. Job titles such as 育儿师/儿陪师/家庭教师/私人助理/高端家务师 go to Job Type only.
25. Extract concrete day-to-day duties into order_info["Job Duties"] as short factual phrases. Do not invent duties.
26. Candidate age limits, gender, hometown exclusions, appearance and personality go only to manual_review.
27. Do not invent qualifications not stated.

COMBINATION-LOGIC RULES:
- All ordinary fields inside hard_requirements are AND conditions by default.
- Use compound_requirements ONLY when the employer explicitly gives alternatives or grouped logic such as "A或B", "A或者B", "A/B满足其一", "二选一", "任一即可".
- One compound group has:
  {{
    "Label": "human-readable label",
    "Logic": "OR" or "AND",
    "Options": [
      {{
        "Label": "option label",
        "Requirements": {{
          "Allowed Field": value
        }}
      }}
    ]
  }}
- Multiple fields inside ONE Option are AND conditions.
- For an OR group, satisfying ANY one Option is enough.
- Do not duplicate a condition in both hard_requirements and compound_requirements.

IMPORTANT EXAMPLE:
"5年以上教培经验或3年以上儿陪经验"
must become:
"compound_requirements": [
  {{
    "Label": "教培/儿陪经验",
    "Logic": "OR",
    "Options": [
      {{
        "Label": "5年以上教培经验",
        "Requirements": {{
          "Minimum Years of Teaching / Training Experience": 5
        }}
      }},
      {{
        "Label": "3年以上儿陪经验",
        "Requirements": {{
          "Nanny Educator Experience": true,
          "Minimum Years of Nanny Educator Experience": 3
        }}
      }}
    ]
  }}
]

ANOTHER EXAMPLE:
"有幼儿园经验或早教机构经验"
must become one OR compound group with:
- Option 1: Kindergarten Experience=true
- Option 2: Early Years Experience=true

For ordinary "英语流利且熟练驾驶", put BOTH Teaching Languages=["English"] and Driving Required=true
in hard_requirements. That is already AND, so no compound group is needed.

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
        "compound_requirements": parsed.get("compound_requirements", []),
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
                "组合条件数": len(parsed.get("compound_requirements", [])),
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


def is_data_insufficient(item: Dict[str, Any]) -> bool:
    """No confirmed hard-condition evidence and no hard conflict = insufficient data, not a true 0% fit."""
    hard = item.get("hard", {})
    return (
        item.get("status") == "pending"
        and not hard.get(MATCH, [])
        and not hard.get(CONFLICT, [])
        and bool(hard.get(UNKNOWN, []))
    )


def score_text(item: Dict[str, Any]) -> str:
    if is_data_insufficient(item):
        return "资料不足"
    return f"{int(item.get('score', 0))}%"


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
            st.metric("匹配度", score_text(item))
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

    compound = parsed.get("compound_requirements", [])
    if compound:
        render_compound_requirements(compound)

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
                row[f"Top {candidate_index + 1} 匹配度"] = score_text(item)
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
                "匹配度": score_text(result),
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
    upper = text.upper()

    if "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in lower or "rate limit" in lower:
        st.error("Gemini API 当前额度已达到限制。")
        st.warning(
            "请等待额度恢复或调整 Gemini API 计费/额度后再次运行。"
            "Baserow 老师数据和已经确认的标准订单不受影响。"
        )
    elif (
        "GEMINI_TEMPORARY_UNAVAILABLE" in text
        or "SERVERERROR" in upper
        or "500" in text
        or "503" in text
        or "504" in text
        or "INTERNAL" in upper
        or "UNAVAILABLE" in upper
        or "DEADLINE_EXCEEDED" in upper
    ):
        st.error("Gemini 服务端暂时不可用或处理超时。")
        st.warning(
            "这不是 Baserow、老师照片或 PDF 的错误。"
            "系统已执行 SDK 自动重试，并会尝试一个可用的 Flash 备用模型。"
            "如果仍失败，请稍后再点一次。"
        )
        st.info(
            "如果这条目标订单已经在「标准订单池」里，请直接选择标准订单池。"
            "老师匹配和基于已标准化订单的反向匹配不需要重新调用 Gemini。"
        )
    elif isinstance(exc, ValueError):
        st.warning(text)
    elif "json" in lower and ("gemini" in lower or "格式" in text or "不完整" in text):
        st.error("Gemini 返回的结构化结果不完整。")
        st.info(
            "请重新运行一次。批量模式会自动分成小批次解析，"
            "避免一次返回太长导致 JSON 截断。"
        )
    else:
        st.error("处理过程中发生错误。")
        st.exception(exc)



# ============================================================
# 8C. V2.2.5 JOB-TARGETED RESUME OPTIMIZER
# ============================================================


def teacher_job_relevant_profile(teacher: Dict[str, Any]) -> Dict[str, Any]:
    """Return a conservative, job-relevant fact payload for resume tailoring.

    We intentionally exclude internal IDs and avoid using candidate age, gender,
    nationality/hometown or appearance as tailoring signals.  If those facts are
    already present in a pasted original resume, Gemini is told not to emphasize,
    hide, or alter them to satisfy employer preferences.
    """
    excluded = {
        "Baserow ID", "Age", "Birth Date", "Date of Birth", "DOB", "Gender",
        "Nationality", "Hometown", "Height", "Weight", "Photo", "Image",
        "Teacher Photo", "Profile Photo", "Original Resume", "Full Resume",
        "Resume", "CV", "Resume Text",
    }
    result: Dict[str, Any] = {}
    for key, value in teacher.items():
        if str(key).startswith("_") or key in excluded:
            continue
        if value is None or value == "" or value == [] or value == {}:
            continue
        result[str(key)] = value
    return result


def teacher_resume_source(teacher: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Return the best available original resume text and its Baserow source field.

    V2.2.5 treats ``Original Resume`` as the canonical full-resume field.
    Older/fallback field names are still supported so existing databases continue
    to work.  The function never fabricates missing resume text.
    """
    preferred_fields = [
        "Original Resume",
        "Full Resume",
        "Resume",
        "CV",
        "Resume Text",
    ]

    for field in preferred_fields:
        value = teacher.get(field)
        if value is None or value == "" or value == []:
            continue

        if isinstance(value, list):
            body = "\n".join(str(x) for x in value if x not in (None, ""))
        else:
            body = str(value).strip()

        if body:
            return body, field

    # Conservative fallback: these fields are not guaranteed to be a complete CV,
    # so concatenate them only when no dedicated resume field exists.
    fallback_fields = [
        "Experience Summary",
        "Profile",
        "Biography",
        "Bio",
        "Notes",
    ]
    sections: List[str] = []

    for field in fallback_fields:
        value = teacher.get(field)
        if value is None or value == "" or value == []:
            continue

        if isinstance(value, list):
            body = "\n".join(str(x) for x in value if x not in (None, ""))
        else:
            body = str(value).strip()

        if body:
            sections.append(f"【{field}】\n{body}")

    if sections:
        return "\n\n".join(sections).strip(), "结构化简介/备注字段"

    return "", None


def teacher_resume_source_hint(teacher: Dict[str, Any]) -> str:
    """Backward-compatible wrapper used by older code paths."""
    resume_text, _source_field = teacher_resume_source(teacher)
    return resume_text


def safe_order_payload_for_resume(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Only job-relevant order content is sent as tailoring criteria.

    manual_review is deliberately excluded so age/gender/hometown/appearance
    preferences cannot drive resume optimization.
    """
    info = dict(parsed.get("order_info", {}) or {})
    return {
        "order_info": info,
        "hard_requirements": parsed.get("hard_requirements", {}) or {},
        "preferred_requirements": parsed.get("preferred_requirements", {}) or {},
        "reference_requirements": parsed.get("reference_requirements", {}) or {},
        "compound_requirements": parsed.get("compound_requirements", []) or [],
    }


def collect_available_standard_orders() -> List[Dict[str, Any]]:
    """Collect current confirmed/parsed orders from the session and deduplicate them."""
    candidates: List[Dict[str, Any]] = []

    for parsed in st.session_state.get("batch_parsed_orders") or []:
        if isinstance(parsed, dict):
            candidates.append(parsed)

    reverse_orders = st.session_state.get("reverse_parsed_orders") or []
    for parsed in reverse_orders:
        if isinstance(parsed, dict):
            candidates.append(parsed)

    single = st.session_state.get("single_parsed_order")
    if isinstance(single, dict):
        candidates.append(single)

    unique: List[Dict[str, Any]] = []
    seen = set()
    for parsed in candidates:
        payload = safe_order_payload_for_resume(parsed)
        key = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        unique.append(parsed)
    return unique


def build_resume_optimizer_prompt(
    teacher: Dict[str, Any],
    parsed_order: Dict[str, Any],
    original_resume: str,
    supplemental_employer_text: str,
) -> str:
    teacher_payload = teacher_job_relevant_profile(teacher)
    order_payload = safe_order_payload_for_resume(parsed_order)

    # Keep prompts bounded on Community Cloud / Gemini free tiers.
    resume_text = str(original_resume or "").strip()[:30000]
    employer_text = str(supplemental_employer_text or "").strip()[:12000]

    return f"""
You are a factual resume editor for a private-family education / childcare recruitment system.
Create a JOB-TARGETED resume version for ONE teacher and ONE employer order.
Return JSON only. No markdown fences and no prose outside JSON.

NON-NEGOTIABLE FACTUALITY RULES:
1. You may reorganize, shorten, rewrite, and emphasize facts that are explicitly supported by either:
   A) STRUCTURED TEACHER FACTS, or
   B) ORIGINAL TEACHER RESUME.
2. NEVER invent or upgrade employment dates, employer names, job titles, duties, years of experience,
   degree, school, major, certificates, curriculum knowledge, SEN/ADHD experience, Montessori experience,
   language level, driving ability, visa/work authorization, night care, cooking, childcare or any other skill.
3. A job requirement is NOT evidence that the teacher has that capability.
4. If evidence is missing or ambiguous, do NOT write the claim into the tailored resume. Put it in
   questions_to_confirm and mark the requirement evidence as "missing" or "partial".
5. Do not convert a visa into work authorization. Do not convert "serving a child who attends an
   international school" into "worked as an international-school teacher". Do not infer IB/AP/etc.
6. Do not turn IELTS / conversational English into "full English teaching" unless the source explicitly supports it.
7. Preserve chronology and factual dates. You may reorder bullet emphasis INSIDE an existing role, but do not
   fabricate a new role or change employment dates.
8. The employer's candidate age, gender, nationality/hometown, appearance, height/weight or similar personal
   preferences must NOT influence the rewrite. Do not add, remove, hide or emphasize personal traits to satisfy them.
9. Do not claim a requirement is satisfied merely because it appears in the employer text.

TAILORING GOAL:
- Lead with the teacher's strongest TRUE evidence for this job.
- Use concise professional Chinese suitable for sending to a recruiter or private-family employer.
- Generate TWO clearly different resume versions in this SAME response:
  A) FULL VERSION: complete job-targeted resume, normally 2-4 pages after PDF layout.
  B) BRIEF VERSION: genuinely condensed one-page style resume. It must NOT simply repeat or truncate the full version.
- The FULL version should preserve the teacher's relevant chronology and fuller work-history detail.
- The BRIEF version should contain only the most useful content for this target job:
  * brief summary around 70-120 Chinese characters;
  * no more than 4 core strengths;
  * 2-4 most relevant work roles, normally no more than 2 concise duty/achievement lines per role;
  * older or weakly relevant roles may be combined into one short “其他经历” line;
  * education should be concise;
  * certificates/qualifications may remain vertically listed when confirmed, but do not repeat them elsewhere.
- The BRIEF version should normally be materially shorter than the FULL version (aim for roughly 40%-60% of the full resume body).
- ALL visible resume section headings must be Chinese. Do not use PROFILE, CORE STRENGTHS, EXPERIENCE, EDUCATION, SKILLS, CONTACT, CERTIFICATES or other English section headings.
- Prefer Chinese headings such as：个人简介、核心优势、工作经历、教育背景、证书与资质、专业技能、语言能力、其他信息。
- professional_summary / core_strengths are rendered separately by the PDF template. Therefore tailored_resume_markdown and brief_resume_markdown should normally START from 工作经历 and should NOT repeat 个人简介、个人总结 or 核心优势.
- In 证书与资质, list every confirmed certificate / qualification on its own separate line. Do not join several certificates in one horizontal sentence.
- Use a vertical single-column reading order. Do not design side-by-side columns or mix a left sidebar with a right content column.
- Do not put match scores, requirement tables, reasoning, evidence labels, conflicts, or pending-confirmation items into either resume body.
- Evidence and confirmation items belong only in requirement_evidence / questions_to_confirm for the web interface, not in the resume body.
- Keep unsupported requirements out of the resume and surface them for human confirmation.
- Do not use markdown emphasis symbols such as **, __, *word*, _word_, or backticks inside visible resume sentences. Headings may use ## only as structural markers because the PDF renderer removes them.

RETURN EXACTLY THIS JSON STRUCTURE:
{{
  "resume_title": "short targeted professional headline",
  "professional_summary": "120-220 Chinese characters, factual and job-targeted for the FULL version",
  "core_strengths": ["full-version fact-based strength 1", "full-version fact-based strength 2"],
  "tailored_resume_markdown": "FULL resume body. Chinese headings only. Normally start with ## 工作经历; include fuller relevant chronology, education, qualifications and skills as appropriate. Do not repeat 个人简介/个人总结/核心优势 because those are rendered separately. No markdown emphasis symbols.",
  "brief_professional_summary": "70-120 Chinese characters, factual and job-targeted for the BRIEF version",
  "brief_core_strengths": ["maximum 4 concise job-relevant strengths"],
  "brief_resume_markdown": "GENUINELY CONDENSED brief resume body, materially shorter than tailored_resume_markdown. Chinese headings only. Keep only 2-4 most relevant roles, normally max 2 concise lines per role; combine less-relevant history into a short 其他经历 when useful. Do not repeat 个人简介/个人总结/核心优势. No markdown emphasis symbols.",
  "employer_recommendation": "150-300 Chinese characters for recruiter/employer recommendation",
  "requirement_evidence": [
    {{
      "Requirement": "job requirement",
      "Status": "supported | partial | missing",
      "Evidence": "specific fact from teacher data/resume, or 资料中未找到明确证据"
    }}
  ],
  "questions_to_confirm": ["only questions that materially affect this target job"],
  "content_deemphasized": ["true but less relevant content that was compressed or moved later"],
  "factuality_notes": ["any ambiguity/conflict that a human should review"]
}}

STRUCTURED TEACHER FACTS:
{json.dumps(teacher_payload, ensure_ascii=False, indent=2, default=str)}

ORIGINAL TEACHER RESUME:
{resume_text if resume_text else "[No full original resume pasted. Use structured facts only and stay conservative.]"}

TARGET JOB - SAFE STRUCTURED REQUIREMENTS:
{json.dumps(order_payload, ensure_ascii=False, indent=2, default=str)}

OPTIONAL FULL EMPLOYER TEXT:
{employer_text if employer_text else "[Not provided]"}

Remember: personal-trait preferences in employer text are irrelevant to the rewrite. Use only job-relevant duties,
qualifications, work conditions and teacher-supported evidence.
"""


def generate_tailored_resume(
    teacher: Dict[str, Any],
    parsed_order: Dict[str, Any],
    original_resume: str,
    supplemental_employer_text: str,
) -> Tuple[Dict[str, Any], str]:
    prompt = build_resume_optimizer_prompt(
        teacher=teacher,
        parsed_order=parsed_order,
        original_resume=original_resume,
        supplemental_employer_text=supplemental_employer_text,
    )
    payload, model_used = generate_json_prompt(prompt)

    if not isinstance(payload, dict):
        raise RuntimeError("Gemini 简历优化返回的顶层内容不是 JSON object。")

    # Resume optimizer must not accidentally return the order-parser wrapper.
    if "orders" in payload and len(payload) == 1:
        raise RuntimeError("Gemini 返回了订单格式而不是简历格式，请重新生成一次。")

    required_keys = {
        "resume_title", "professional_summary", "tailored_resume_markdown",
        "brief_professional_summary", "brief_resume_markdown",
        "employer_recommendation", "requirement_evidence", "questions_to_confirm",
    }
    if not required_keys.intersection(payload.keys()):
        raise RuntimeError("Gemini 返回内容缺少定制简历字段，请重新生成一次。")

    payload.setdefault("resume_title", "")
    payload.setdefault("professional_summary", "")
    payload.setdefault("core_strengths", [])
    payload.setdefault("tailored_resume_markdown", "")
    payload.setdefault("brief_professional_summary", "")
    payload.setdefault("brief_core_strengths", [])
    payload.setdefault("brief_resume_markdown", "")
    payload.setdefault("employer_recommendation", "")
    payload.setdefault("requirement_evidence", [])
    payload.setdefault("questions_to_confirm", [])
    payload.setdefault("content_deemphasized", [])
    payload.setdefault("factuality_notes", [])

    if not isinstance(payload.get("requirement_evidence"), list):
        payload["requirement_evidence"] = []
    if not isinstance(payload.get("questions_to_confirm"), list):
        payload["questions_to_confirm"] = [str(payload.get("questions_to_confirm"))]
    if not isinstance(payload.get("core_strengths"), list):
        payload["core_strengths"] = [str(payload.get("core_strengths"))]
    if not isinstance(payload.get("brief_core_strengths"), list):
        payload["brief_core_strengths"] = [str(payload.get("brief_core_strengths"))]
    payload["brief_core_strengths"] = [
        str(x).strip()
        for x in payload.get("brief_core_strengths", [])
        if str(x).strip()
    ][:4]
    if not isinstance(payload.get("content_deemphasized"), list):
        payload["content_deemphasized"] = [str(payload.get("content_deemphasized"))]
    if not isinstance(payload.get("factuality_notes"), list):
        payload["factuality_notes"] = [str(payload.get("factuality_notes"))]

    if not str(payload.get("brief_professional_summary") or "").strip():
        payload["brief_professional_summary"] = str(
            payload.get("professional_summary") or ""
        ).strip()[:180]

    if not str(payload.get("brief_resume_markdown") or "").strip():
        # This fallback is only for resilience. New prompts should return a true
        # brief version directly; do not call Gemini a second time just for the PDF.
        payload["brief_resume_markdown"] = str(
            payload.get("tailored_resume_markdown") or ""
        ).strip()

    return payload, model_used


def resume_evidence_rows(result: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in result.get("requirement_evidence", []) or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("Status") or "").strip().lower()
        status_cn = {
            "supported": "✅ 有证据",
            "partial": "⚠️ 部分证据",
            "missing": "❓ 缺少证据",
        }.get(status, status or "待复核")
        rows.append({
            "岗位要求": str(item.get("Requirement") or ""),
            "证据状态": status_cn,
            "老师简历/资料证据": str(item.get("Evidence") or ""),
        })
    return rows


def resume_download_text(result: Dict[str, Any]) -> str:
    parts = []
    title = str(result.get("resume_title") or "").strip()
    summary = str(result.get("professional_summary") or "").strip()
    body = str(result.get("tailored_resume_markdown") or "").strip()
    recommendation = str(result.get("employer_recommendation") or "").strip()

    if title:
        parts.append(title)
    if summary:
        parts.append("【岗位定制简介】\n" + summary)
    if body:
        parts.append(body)
    if recommendation:
        parts.append("【候选人推荐语】\n" + recommendation)
    return "\n\n".join(parts).strip()


# ============================================================
# 8D. V2.2.5 PDF RESUME EXPORT
# ============================================================


def register_pdf_cjk_font() -> str:
    """Use ReportLab's built-in CJK CID font; no external font file is required."""
    if not PDF_EXPORT_AVAILABLE:
        raise RuntimeError(
            "PDF组件尚未安装。请确认 requirements.txt 包含 reportlab 和 Pillow。"
        )
    font_name = "STSong-Light"
    try:
        pdfmetrics.getFont(font_name)
    except Exception:
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    return font_name


def clean_markdown_inline(text: str) -> str:
    """Return plain resume text with markdown/control symbols removed.

    This deliberately removes both well-formed and stray markdown markers, e.g.
    **重点**, _重点_, trailing **, backticks, and accidental heading markers.
    """
    value = str(text or "")
    value = value.replace("\\", "")
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"__(.*?)__", r"\1", value)
    value = re.sub(r"(?<!\w)[*_]{1,3}", "", value)
    value = re.sub(r"[*_]{1,3}(?!\w)", "", value)
    value = value.replace("**", "").replace("__", "")
    value = value.replace("*", "").replace("_", "").replace("`", "")
    value = re.sub(r"^#+\s*", "", value)
    value = re.sub(r"\s+([：:，。,；;])", r"\1", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = value.strip()
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return value


def prepared_photo_bytes(photo_bytes: bytes) -> Optional[BytesIO]:
    """Prepare a rectangular portrait image for non-template uses."""
    if not PDF_EXPORT_AVAILABLE:
        return None
    if not photo_bytes:
        return None
    try:
        with PILImage.open(BytesIO(photo_bytes)) as image:
            image = image.convert("RGB")
            image = ImageOps.fit(
                image,
                (700, 875),
                method=PILImage.Resampling.LANCZOS,
                centering=(0.5, 0.42),
            )
            output = BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            output.seek(0)
            return output
    except Exception:
        return None


def prepared_circle_photo_bytes(photo_bytes: bytes) -> Optional[BytesIO]:
    """Crop a teacher photo into the clean circular portrait used by the CV template."""
    if not PDF_EXPORT_AVAILABLE or not photo_bytes:
        return None
    try:
        with PILImage.open(BytesIO(photo_bytes)) as image:
            image = image.convert("RGB")
            image = ImageOps.fit(
                image,
                (900, 900),
                method=PILImage.Resampling.LANCZOS,
                centering=(0.5, 0.40),
            )
            mask = PILImage.new("L", (900, 900), 0)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(mask)
            draw.ellipse((10, 10, 890, 890), fill=255)

            background = PILImage.new("RGB", (900, 900), (232, 233, 235))
            background.paste(image, (0, 0), mask)
            output = BytesIO()
            background.save(output, format="PNG", optimize=True)
            output.seek(0)
            return output
    except Exception:
        return None


def markdownish_resume_flowables(
    text: str,
    body_style: ParagraphStyle,
    heading_style: ParagraphStyle,
    subheading_style: ParagraphStyle,
    bullet_style: ParagraphStyle,
) -> List[Any]:
    """Render only resume content, deliberately excluding matching/reasoning sections."""
    flowables: List[Any] = []
    blocked_section = False
    blocked_keywords = {
        "岗位要求", "匹配", "推荐理由", "候选人推荐", "事实校验",
        "证据对照", "待确认", "人工确认", "匹配原则", "匹配思路",
        "为什么推荐", "资料缺口", "风险提示",
        # These are already rendered from dedicated JSON fields above the body.
        "个人简介", "个人总结", "核心优势",
        "PROFILE", "PROFESSIONAL SUMMARY", "CORE STRENGTHS",
    }

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            if not blocked_section:
                flowables.append(Spacer(1, 1.6 * mm))
            continue

        heading_text = line.lstrip("# ").strip()
        is_heading = line.startswith("#")
        if is_heading:
            blocked_section = any(keyword in heading_text for keyword in blocked_keywords)
            if blocked_section:
                continue
        elif blocked_section:
            continue

        # Defensive filtering in case the model accidentally includes analysis as plain text.
        if any(
            line.startswith(prefix)
            for prefix in [
                "匹配度", "岗位匹配度", "硬条件确认度", "匹配状态",
                "岗位要求 ↔", "岗位要求↔", "待确认：", "冲突：",
            ]
        ):
            continue

        if line.startswith("### "):
            flowables.append(Paragraph(clean_markdown_inline(line[4:]), subheading_style))
            flowables.append(Spacer(1, 0.8 * mm))
            continue

        if line.startswith("## "):
            flowables.append(Paragraph(clean_markdown_inline(line[3:]), heading_style))
            flowables.append(Spacer(1, 1.1 * mm))
            continue

        if line.startswith("# "):
            flowables.append(Paragraph(clean_markdown_inline(line[2:]), heading_style))
            flowables.append(Spacer(1, 1.1 * mm))
            continue

        if line.startswith(("•", "-", "*", "·")):
            content = line.lstrip("•-*· ").strip()
            if content:
                # Keep the visual list indentation, but do not print markdown markers.
                flowables.append(Paragraph(clean_markdown_inline(content), bullet_style))
            continue

        flowables.append(Paragraph(clean_markdown_inline(line), body_style))

    return flowables


def pdf_teacher_display_value(value: Any) -> str:
    if value is None or value == "" or value == []:
        return ""
    if isinstance(value, dict):
        return str(value.get("value") or value.get("name") or "").strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            rendered = pdf_teacher_display_value(item)
            if rendered:
                parts.append(rendered)
        return ", ".join(dedupe(parts))
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value).strip()


def pdf_teacher_first(teacher: Dict[str, Any], *fields: str) -> str:
    for field in fields:
        rendered = pdf_teacher_display_value(teacher.get(field))
        if rendered:
            return rendered
    return ""


def pdf_teacher_sidebar_sections(teacher: Dict[str, Any]) -> List[Tuple[str, List[str]]]:
    """Build concise sidebar facts. These are resume facts, not matching analysis."""
    basics: List[str] = []
    city = pdf_teacher_first(teacher, "Current City")
    country = pdf_teacher_first(teacher, "Current Country")
    location = ", ".join(x for x in [city, country] if x)
    if location:
        basics.append(f"所在地：{location}")

    degree = pdf_teacher_first(teacher, "Highest Degree")
    if degree:
        basics.append(f"学历：{degree}")

    major = pdf_teacher_first(teacher, "Major")
    if major:
        basics.append(f"专业：{major}")

    languages = pdf_teacher_first(teacher, "Teaching Languages")
    if languages:
        basics.append(f"语言：{languages}")

    driving = boolish(teacher.get("Driving"))
    if driving is True:
        basics.append("驾驶：会")

    live_in = boolish(teacher.get("Live-in"))
    if live_in is True:
        basics.append("住家：可")

    child_min = to_number(teacher.get("Minimum Child Age"))
    child_max = to_number(teacher.get("Maximum Child Age"))
    if child_min is not None and child_max is not None:
        basics.append(f"孩子年龄：{child_min:g}-{child_max:g}岁")
    elif child_min is not None:
        basics.append(f"孩子年龄：{child_min:g}岁以上")
    elif child_max is not None:
        basics.append(f"孩子年龄：{child_max:g}岁以下")

    contact: List[str] = []
    for label, fields in [
        ("电话", ("Phone", "Mobile", "Phone Number")),
        ("邮箱", ("Email",)),
        ("微信", ("WeChat", "Wechat")),
    ]:
        value = pdf_teacher_first(teacher, *fields)
        if value:
            contact.append(f"{label}：{value}")

    skills: List[str] = []
    subjects = pdf_teacher_first(teacher, "Subjects")
    if subjects:
        skills.append(subjects)
    curriculum = pdf_teacher_first(teacher, "Curriculum")
    if curriculum:
        skills.append(curriculum)
    certificates = pdf_teacher_first(teacher, "Certificates", "Required Certificates")
    if certificates:
        skills.append(certificates)

    boolean_skill_map = [
        ("Early Years Experience", "早教"),
        ("General Tutoring Experience", "全科辅导"),
        ("Family-School Communication", "家校沟通"),
        ("Child Psychology Experience", "儿童心理"),
        ("Cooking", "烹饪"),
        ("Nanny Educator Experience", "教育陪伴/教育管家"),
    ]
    for field, label in boolean_skill_map:
        if boolish(teacher.get(field)) is True and label not in skills:
            skills.append(label)

    sections: List[Tuple[str, List[str]]] = []
    if basics:
        sections.append(("基本信息", basics[:8]))
    if contact:
        sections.append(("联系方式", contact[:5]))
    if skills:
        sections.append(("核心技能", skills[:9]))
    return sections


def draw_resume_sidebar(
    canvas: Any,
    doc: Any,
    teacher: Dict[str, Any],
    teacher_name_text: str,
    headline: str,
    photo_bytes: Optional[bytes],
    font_name: str,
) -> None:
    """Draw the fixed grey sidebar inspired by the user's clean CV reference."""
    page_w, page_h = A4
    sidebar_w = 59 * mm
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#E9EAEC"))
    canvas.rect(0, 0, sidebar_w, page_h, stroke=0, fill=1)

    # Circular portrait.
    circle_photo = prepared_circle_photo_bytes(photo_bytes or b"")
    photo_size = 32 * mm
    photo_x = (sidebar_w - photo_size) / 2
    photo_y = page_h - 19 * mm - photo_size
    if circle_photo:
        canvas.drawImage(
            ImageReader(circle_photo),
            photo_x,
            photo_y,
            width=photo_size,
            height=photo_size,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        canvas.setFillColor(colors.HexColor("#D6D8DC"))
        canvas.circle(sidebar_w / 2, photo_y + photo_size / 2, photo_size / 2, stroke=0, fill=1)

    left = 10 * mm
    content_w = sidebar_w - 20 * mm
    y = photo_y - 9 * mm

    name_style = ParagraphStyle(
        "sidebar_name",
        fontName=font_name,
        fontSize=16,
        leading=19,
        textColor=colors.HexColor("#24262C"),
        alignment=TA_LEFT,
    )
    title_style = ParagraphStyle(
        "sidebar_title",
        fontName=font_name,
        fontSize=8.2,
        leading=11,
        textColor=colors.HexColor("#5C616B"),
        alignment=TA_LEFT,
    )
    section_style = ParagraphStyle(
        "sidebar_section",
        fontName="Helvetica-Bold",
        fontSize=8.8,
        leading=11,
        textColor=colors.HexColor("#24262C"),
        alignment=TA_LEFT,
    )
    item_style = ParagraphStyle(
        "sidebar_item",
        fontName=font_name,
        fontSize=7.6,
        leading=10.7,
        textColor=colors.HexColor("#40444D"),
        alignment=TA_LEFT,
    )

    p = Paragraph(clean_markdown_inline(teacher_name_text), name_style)
    _, h = p.wrap(content_w, 30 * mm)
    p.drawOn(canvas, left, y - h)
    y -= h + 2 * mm

    if headline:
        p = Paragraph(clean_markdown_inline(headline), title_style)
        _, h = p.wrap(content_w, 24 * mm)
        p.drawOn(canvas, left, y - h)
        y -= h + 5 * mm

    canvas.setStrokeColor(colors.HexColor("#AEB2B8"))
    canvas.setLineWidth(0.5)
    canvas.line(left, y, sidebar_w - 9 * mm, y)
    y -= 6 * mm

    sections = pdf_teacher_sidebar_sections(teacher)
    english_labels = {
        "基本信息": "PROFILE",
        "联系方式": "CONTACT",
        "核心技能": "SKILLS",
    }
    for section_name, items in sections:
        if y < 28 * mm:
            break
        section_label = english_labels.get(section_name, section_name.upper())
        p = Paragraph(section_label, section_style)
        _, h = p.wrap(content_w, 10 * mm)
        p.drawOn(canvas, left, y - h)
        y -= h + 2.5 * mm

        for item in items:
            if y < 18 * mm:
                break
            p = Paragraph(clean_markdown_inline(item), item_style)
            _, h = p.wrap(content_w, 18 * mm)
            p.drawOn(canvas, left, y - h)
            y -= h + 1.3 * mm
        y -= 4 * mm

    # Discreet page number only. No matching logic, score, evidence or reasoning.
    canvas.setFillColor(colors.HexColor("#8A8E96"))
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(left, 8 * mm, f"PAGE {doc.page}")
    canvas.restoreState()


def normalize_resume_heading_text(value: str) -> str:
    """Force common English CV headings into Chinese for PDF export."""
    raw = str(value or "")
    replacements = {
        "PROFILE": "个人简介",
        "PROFESSIONAL SUMMARY": "个人简介",
        "SUMMARY": "个人简介",
        "CORE STRENGTHS": "核心优势",
        "STRENGTHS": "核心优势",
        "EXPERIENCE": "工作经历",
        "WORK EXPERIENCE": "工作经历",
        "EDUCATION": "教育背景",
        "CERTIFICATES": "证书与资质",
        "CERTIFICATIONS": "证书与资质",
        "QUALIFICATIONS": "证书与资质",
        "CERTIFICATES & QUALIFICATIONS": "证书与资质",
        "SKILLS": "专业技能",
        "CONTACT": "联系方式",
        "LANGUAGES": "语言能力",
        "AWARDS": "荣誉与奖项",
        "REFERENCES": "推荐人",
    }

    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        prefix = ""
        body = stripped
        if stripped.startswith("### "):
            prefix, body = "### ", stripped[4:].strip()
        elif stripped.startswith("## "):
            prefix, body = "## ", stripped[3:].strip()
        elif stripped.startswith("# "):
            prefix, body = "# ", stripped[2:].strip()

        key = body.upper().strip().rstrip(":：")
        if key in replacements:
            body = replacements[key]
        lines.append(prefix + body if stripped else "")
    return "\n".join(lines)


def split_vertical_items(value: Any) -> List[str]:
    """Split multi-value teacher fields into individual vertical display items."""
    raw_items = ensure_list(value)
    result: List[str] = []

    for raw in raw_items:
        if raw is None:
            continue
        if isinstance(raw, dict):
            raw = raw.get("value") or raw.get("name") or raw.get("text") or ""
        text_value = str(raw).strip()
        if not text_value:
            continue

        # Separate common multi-value delimiters, but do not split normal prose.
        parts = re.split(r"[,，;；|]+", text_value)
        if len(parts) == 1:
            parts = [text_value]

        for part in parts:
            clean = str(part).strip()
            if clean and clean not in result:
                result.append(clean)

    return result


def pdf_teacher_vertical_sections(
    teacher: Dict[str, Any],
) -> Dict[str, List[str]]:
    """Prepare Chinese, vertically stacked teacher metadata for the PDF."""
    basics: List[str] = []
    city = pdf_teacher_first(teacher, "Current City")
    country = pdf_teacher_first(teacher, "Current Country")
    location = "，".join(x for x in [city, country] if x)
    if location:
        basics.append(f"所在地：{location}")

    degree = pdf_teacher_first(teacher, "Highest Degree")
    if degree:
        basics.append(f"学历：{degree}")

    university = pdf_teacher_first(teacher, "University", "School")
    if university:
        basics.append(f"毕业院校：{university}")

    major = pdf_teacher_first(teacher, "Major")
    if major:
        basics.append(f"专业：{major}")

    languages = split_vertical_items(teacher.get("Teaching Languages"))
    if languages:
        basics.append("语言：" + "、".join(languages))

    driving = boolish(teacher.get("Driving"))
    if driving is True:
        basics.append("驾驶：会")

    live_in = boolish(teacher.get("Live-in"))
    if live_in is True:
        basics.append("住家：可")

    child_min = to_number(teacher.get("Minimum Child Age"))
    child_max = to_number(teacher.get("Maximum Child Age"))
    if child_min is not None and child_max is not None:
        basics.append(f"可接受孩子年龄：{child_min:g}-{child_max:g}岁")
    elif child_min is not None:
        basics.append(f"可接受孩子年龄：{child_min:g}岁以上")
    elif child_max is not None:
        basics.append(f"可接受孩子年龄：{child_max:g}岁以下")

    contact: List[str] = []
    for label, fields in [
        ("电话", ("Phone", "Mobile", "Phone Number")),
        ("邮箱", ("Email",)),
        ("微信", ("WeChat", "Wechat")),
    ]:
        value = pdf_teacher_first(teacher, *fields)
        if value:
            contact.append(f"{label}：{value}")

    skills: List[str] = []
    for field in ["Subjects", "Curriculum"]:
        for item in split_vertical_items(teacher.get(field)):
            if item not in skills:
                skills.append(item)

    boolean_skill_map = [
        ("Early Years Experience", "早教"),
        ("General Tutoring Experience", "全科辅导"),
        ("Family-School Communication", "家校沟通"),
        ("Child Psychology Experience", "儿童心理"),
        ("Cooking", "烹饪"),
        ("Nanny Educator Experience", "教育陪伴 / 教育管家"),
    ]
    for field, label in boolean_skill_map:
        if boolish(teacher.get(field)) is True and label not in skills:
            skills.append(label)

    certificates: List[str] = []
    certificate_fields = [
        "Certificates",
        "Certifications",
        "Qualifications",
        "Licenses",
        "Teaching Certificates",
    ]
    for field in certificate_fields:
        for item in split_vertical_items(teacher.get(field)):
            if item not in certificates:
                certificates.append(item)

    return {
        "基本信息": basics,
        "联系方式": contact,
        "专业技能": skills,
        "证书与资质": certificates,
    }


def build_resume_pdf_bytes(
    teacher_name_text: str,
    resume_result: Dict[str, Any],
    tailored_text: str,
    recommendation_text: str,
    photo_bytes: Optional[bytes] = None,
    mode: str = "full",
    teacher_profile: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Create a clean A4 Chinese resume PDF in ONE vertical column.

    Design principles:
    - Chinese section headings only.
    - One top-to-bottom reading order; no left sidebar / right content column.
    - Teacher photo is centered at the top when available.
    - Certificates / qualifications are displayed one item per line.
    - Matching scores, reasoning, evidence tables, conflicts and pending items
      never appear in the exported resume.
    """
    if not PDF_EXPORT_AVAILABLE:
        raise RuntimeError(
            "PDF导出组件未安装。请在 requirements.txt 中加入 reportlab 和 Pillow，"
            "Commit 后重新 Reboot Streamlit。"
        )

    font_name = register_pdf_cjk_font()
    teacher_profile = teacher_profile or {}
    output = BytesIO()

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"{teacher_name_text} 简历",
        author="AI Teacher Matching System",
    )

    name_style = ParagraphStyle(
        "vertical_cv_name",
        fontName=font_name,
        fontSize=20,
        leading=25,
        textColor=colors.HexColor("#24262C"),
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    title_style = ParagraphStyle(
        "vertical_cv_title",
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#5C616B"),
        alignment=TA_CENTER,
        spaceAfter=3,
    )
    heading_style = ParagraphStyle(
        "vertical_cv_heading",
        fontName=font_name,
        fontSize=12.5,
        leading=16,
        textColor=colors.HexColor("#22252B"),
        spaceBefore=6,
        spaceAfter=3,
    )
    subheading_style = ParagraphStyle(
        "vertical_cv_subheading",
        fontName=font_name,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2C3037"),
        spaceBefore=3,
        spaceAfter=2,
    )
    body_style = ParagraphStyle(
        "vertical_cv_body",
        fontName=font_name,
        fontSize=9.0 if mode == "full" else 8.8,
        leading=13.3,
        textColor=colors.HexColor("#3B3E45"),
        alignment=TA_LEFT,
        spaceAfter=2,
    )
    bullet_style = ParagraphStyle(
        "vertical_cv_bullet",
        fontName=font_name,
        fontSize=9.0 if mode == "full" else 8.8,
        leading=13.0,
        leftIndent=4.3 * mm,
        firstLineIndent=-2.8 * mm,
        textColor=colors.HexColor("#3B3E45"),
        spaceAfter=1.2,
    )
    summary_style = ParagraphStyle(
        "vertical_cv_summary",
        fontName=font_name,
        fontSize=9.3,
        leading=13.8,
        textColor=colors.HexColor("#41454D"),
        alignment=TA_LEFT,
        spaceAfter=2,
    )

    story: List[Any] = []

    # -------------------------
    # Top portrait - vertical.
    # -------------------------
    circle_photo = prepared_circle_photo_bytes(photo_bytes or b"")
    if circle_photo:
        portrait = RLImage(circle_photo, width=30 * mm, height=30 * mm)
        portrait.hAlign = "CENTER"
        story.append(portrait)
        story.append(Spacer(1, 3.5 * mm))

    headline = str(resume_result.get("resume_title") or "").strip()
    if mode == "brief":
        summary = str(
            resume_result.get("brief_professional_summary")
            or resume_result.get("professional_summary")
            or ""
        ).strip()
    else:
        summary = str(resume_result.get("professional_summary") or "").strip()

    story.append(Paragraph(clean_markdown_inline(teacher_name_text), name_style))
    if headline:
        story.append(Paragraph(clean_markdown_inline(headline), title_style))

    # Divider.
    divider = Table([[""]], colWidths=[174 * mm], rowHeights=[0.7 * mm])
    divider.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#C7C9CD")),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(Spacer(1, 2 * mm))
    story.append(divider)
    story.append(Spacer(1, 3.5 * mm))

    # -------------------------
    # Structured Baserow data.
    # -------------------------
    structured = pdf_teacher_vertical_sections(teacher_profile)

    basics = structured.get("基本信息", [])
    if basics:
        story.append(Paragraph("基本信息", heading_style))
        for item in basics:
            story.append(Paragraph(clean_markdown_inline(item), body_style))

    contact = structured.get("联系方式", [])
    if contact:
        story.append(Paragraph("联系方式", heading_style))
        for item in contact:
            story.append(Paragraph(clean_markdown_inline(item), body_style))

    # -------------------------
    # Profile and strengths.
    # -------------------------
    if summary:
        story.append(Paragraph("个人简介", heading_style))
        story.append(Paragraph(clean_markdown_inline(summary), summary_style))

    strength_source = (
        resume_result.get("brief_core_strengths", [])
        if mode == "brief"
        else resume_result.get("core_strengths", [])
    )
    strengths = [
        str(x).strip()
        for x in strength_source
        if str(x).strip()
    ]
    if strengths:
        story.append(Paragraph("核心优势", heading_style))
        for item in strengths[:4 if mode == "brief" else 8]:
            story.append(Paragraph(clean_markdown_inline(item), bullet_style))

    # -------------------------
    # Certificates: one per line.
    # -------------------------
    certificates = structured.get("证书与资质", [])
    if certificates:
        story.append(Paragraph("证书与资质", heading_style))
        for certificate in certificates:
            story.append(
                Paragraph(clean_markdown_inline(certificate), bullet_style)
            )

    # -------------------------
    # Skills: vertical only.
    # -------------------------
    skills = structured.get("专业技能", [])
    if skills:
        story.append(Paragraph("专业技能", heading_style))
        for skill in skills[:6 if mode == "brief" else 10]:
            story.append(Paragraph(clean_markdown_inline(skill), bullet_style))

    # -------------------------
    # Gemini resume body.
    # Force English headings to Chinese if they slipped through.
    # -------------------------
    cleaned_tailored_text = normalize_resume_heading_text(tailored_text)

    resume_flowables = markdownish_resume_flowables(
        cleaned_tailored_text,
        body_style,
        heading_style,
        subheading_style,
        bullet_style,
    )

    story.extend(resume_flowables)

    # No recommendation analysis / evidence / pending questions in PDF.
    doc.build(story)
    return output.getvalue()



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
    st.caption("V2.2.5 · 匹配 / 订单定制简历 / 事实校验")
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
        load_baserow_fields.clear()
        st.rerun()

    st.divider()
    st.info(
        "单个订单模式：1 次 Gemini 请求。\n\n"
        "批量模式：① Gemini 用 1 次请求把不同平台订单统一成标准格式；"
        "② 人工确认；③ Python 本地匹配，0 次额外 Gemini。\n\n"
        "老师反向匹配复用标准订单池：0 次新的 Gemini 请求。\n\n"
        "岗位定制简历：每次生成使用 1 次 Gemini 请求；只允许重组和突出已有真实经历，不允许虚构。\n\n"
        "新老师录入：AI解析 1 次；人工确认后写入 Baserow 不再调用 Gemini；照片可保存到 Teacher Photo。"
    )


# ============================================================
# 11. HEADER / MODE SELECTOR
# ============================================================

st.markdown('<div class="main-title">AI Teacher Matching System</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="main-subtitle">V2.2.5：标准订单 → 老师匹配 → 新老师自动入库/照片 → 自动读取 Baserow 原始简历 → 生成带照片的岗位定制 PDF。</div>',
    unsafe_allow_html=True,
)

mode = st.radio(
    "选择匹配模式",
    [
        "① 单个订单 → 匹配全部老师",
        "② 批量订单 → 每单推荐老师",
        "③ 选择老师 → 匹配全部订单",
        "④ 根据订单优化老师简历",
        "⑤ 新老师录入 → 保存到 Baserow",
    ],
    horizontal=True,
)


# ============================================================
# 12. MODE 1 - SINGLE ORDER
# ============================================================

if mode == "① 单个订单 → 匹配全部老师":
    st.markdown('<div class="section-title">单个订单匹配</div>', unsafe_allow_html=True)
    st.caption("粘贴 1 条订单。Gemini 解析 1 次，并识别 A或B / A且B 等组合条件，然后本地 Python 与 Baserow 中全部老师匹配。")

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
        best_item = single_results[0] if single_results else None

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("候选人数", len(single_results))
        with m2:
            st.metric("硬条件确认匹配", confirmed)
        with m3:
            st.metric("需要人工确认", pending)
        with m4:
            st.metric("最高匹配度", score_text(best_item) if best_item else "无")
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
        "V2.2.5 批量匹配继续使用两阶段流程：先让 Gemini 把不同平台、不同排版的原始派单统一成标准订单格式，并识别 OR/AND 组合条件；"
        "你确认/修改以后，再由 Python 本地读取标准订单并匹配全部老师。像“5年教培或3年儿陪”会保留为一个 OR 组合条件；“开车接送”只计驾驶，不再重复计一次接送硬条件。"
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
            best_text = f" · Top1 {results[0]['name']} {score_text(results[0])}" if results else ""
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

elif mode == "③ 选择老师 → 匹配全部订单":
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
            with st.expander(f"{rank}. {title} · {score_text(item)} · {status_text(item['status'])}"):
                render_parsed_order_compact(parsed)
                render_compact_candidate(1, item)



# ============================================================
# 15. MODE 4 - JOB-TARGETED RESUME OPTIMIZATION
# ============================================================

elif mode == "④ 根据订单优化老师简历":
    st.markdown('<div class="section-title">根据目标订单优化老师简历</div>', unsafe_allow_html=True)
    st.caption(
        "选择老师和目标订单后，系统会优先从 Baserow 的 Original Resume 自动读取老师完整简历，"
        "再由 Gemini 重新组织、突出和改写已有真实经历。"
        "任何简历/数据库中没有证据的能力都会进入『待确认』，不会为了迎合岗位而虚构。"
    )

    if not teachers:
        st.warning("老师数据库为空。")
        st.stop()

    teacher_indexes_v20 = list(range(len(teachers)))
    resume_teacher_index = st.selectbox(
        "① 选择老师",
        teacher_indexes_v20,
        format_func=lambda index: teacher_name(teachers[index]),
        key="resume_optimizer_teacher_select_v20",
    )
    resume_teacher = teachers[resume_teacher_index]

    photo_url = teacher_photo_url(resume_teacher)
    if photo_url:
        pc1, pc2 = st.columns([1, 5])
        with pc1:
            st.image(photo_url, width=140, caption="Baserow 老师照片")
        with pc2:
            st.success("✅ 已检测到老师照片；生成 PDF 时可以自动带入。")
    else:
        st.caption("当前老师没有 Teacher Photo；仍可生成无照片 PDF。")

    available_orders = collect_available_standard_orders()
    parsed_target: Optional[Dict[str, Any]] = None

    st.markdown("### ② 选择目标订单")
    if available_orders:
        source_mode = st.radio(
            "订单来源",
            ["使用当前标准订单池", "粘贴一条新的雇主需求"],
            horizontal=True,
            key="resume_order_source_mode_v20",
        )
    else:
        source_mode = "粘贴一条新的雇主需求"
        st.info("当前还没有标准订单池。可以先在这里粘贴一条订单，或先去『② 批量订单』建立标准订单池。")

    if source_mode == "使用当前标准订单池":
        order_indexes_v20 = list(range(len(available_orders)))
        selected_order_index = st.selectbox(
            "目标订单",
            order_indexes_v20,
            format_func=lambda index: order_title(available_orders[index], index + 1),
            key="resume_optimizer_order_select_v20",
        )
        parsed_target = available_orders[selected_order_index]
    else:
        resume_raw_order = st.text_area(
            "粘贴 1 条目标雇主需求",
            height=220,
            placeholder="粘贴一条新的雇主订单。这里会调用 Gemini 解析 1 次。若订单已在标准订单池中，请直接选择标准订单池（0次新的Gemini解析）。",
            key="resume_optimizer_raw_order_v20",
        )
        p1, p2 = st.columns([4, 1])
        with p1:
            parse_resume_order = st.button(
                "解析这条目标订单",
                type="primary",
                use_container_width=True,
                key="resume_optimizer_parse_order_button_v20",
            )
        with p2:
            clear_resume_order = st.button(
                "清除目标订单",
                use_container_width=True,
                key="resume_optimizer_clear_order_button_v20",
            )

        if clear_resume_order:
            for key in [
                "resume_optimizer_raw_order_v20",
                "resume_optimizer_parsed_order_v20",
                "resume_optimizer_result_v20",
                "resume_optimizer_model_v20",
            ]:
                st.session_state.pop(key, None)
            st.rerun()

        if parse_resume_order:
            if not resume_raw_order.strip():
                st.warning("请先粘贴一条目标订单。")
            else:
                try:
                    with st.spinner("Gemini 正在解析这条目标订单..."):
                        st.session_state["resume_optimizer_parsed_order_v20"] = parse_employer_order(resume_raw_order)
                    st.rerun()
                except Exception as exc:
                    render_api_error(exc)

        parsed_target = st.session_state.get("resume_optimizer_parsed_order_v20")

    if parsed_target:
        st.markdown("### 目标订单确认")
        with st.expander(order_title(parsed_target, 1), expanded=False):
            render_parsed_order_compact(parsed_target)
            manual = parsed_target.get("manual_review", {})
            if manual:
                st.caption("年龄、性别、籍贯、外貌等人工复核信息不会用于简历优化。")

    st.markdown("### ③ 老师原始简历（自动从 Baserow 读取）")
    teacher_identity = str(
        resume_teacher.get("Baserow ID") or teacher_name(resume_teacher)
    ).replace(" ", "_")

    baserow_resume_text, baserow_resume_field = teacher_resume_source(resume_teacher)
    resume_editor_key = f"resume_source_text_v21_{teacher_identity}"

    if resume_editor_key not in st.session_state:
        st.session_state[resume_editor_key] = baserow_resume_text

    if baserow_resume_field:
        if baserow_resume_field == "Original Resume":
            st.success(
                f"✅ 已从 Baserow 的 **Original Resume** 自动读取 "
                f"{len(baserow_resume_text):,} 个字符。"
            )
        else:
            st.info(
                f"ℹ️ Baserow 暂无 `Original Resume`，当前从 **{baserow_resume_field}** "
                f"读取了 {len(baserow_resume_text):,} 个字符。"
            )

        reload_resume = st.button(
            "从 Baserow 重新加载老师原始简历",
            use_container_width=True,
            key=f"reload_resume_from_baserow_v21_{teacher_identity}",
        )
        if reload_resume:
            st.session_state[resume_editor_key] = baserow_resume_text
            st.rerun()
    else:
        st.warning(
            "⚠️ 这位老师在 Baserow 中还没有完整原始简历。"
            "建议在 Teachers 表新增 `Original Resume`（Long text）字段，"
            "把老师完整简历粘贴进去。"
        )

    original_resume_text = st.text_area(
        "老师原始简历（已自动载入，可在本次生成前人工补充）",
        height=520,
        key=resume_editor_key,
        placeholder=(
            "如果 Baserow 中暂时没有 Original Resume，可以先在这里粘贴完整简历。\n"
            "建议正式使用时把完整原始简历统一保存到 Baserow 的 Original Resume 字段。\n"
            "这里的临时修改只影响本次生成，不会覆盖 Baserow 原始数据。"
        ),
    )

    if original_resume_text.strip():
        st.caption(
            f"本次将向简历优化模型提供约 {len(original_resume_text):,} 个字符的老师原始简历。"
            "Baserow 结构化字段仍会同时用于事实校验。"
        )

        try:
            current_field_names = set(baserow_field_map().keys())
        except Exception:
            current_field_names = set()

        if "Original Resume" in current_field_names:
            if st.button(
                "保存当前原始简历到 Baserow",
                use_container_width=True,
                key=f"save_original_resume_v22_{teacher_identity}",
            ):
                try:
                    save_original_resume_for_teacher(
                        resume_teacher,
                        original_resume_text,
                    )
                    load_teachers.clear()
                    st.success("✅ Original Resume 已保存到 Baserow。")
                except Exception as exc:
                    render_api_error(exc)
        else:
            st.caption(
                "如希望永久保存这份完整简历，请先在 Teachers 表新增 "
                "`Original Resume`（Long text）字段。"
            )
    else:
        st.warning(
            "目前没有完整原始简历文本。系统仍可仅根据 Baserow 结构化资料生成保守版，"
            "但工作经历细节会比较少。"
        )

    supplemental_default = ""
    if parsed_target:
        supplemental_default = str(
            parsed_target.get("original_request")
            or parsed_target.get("source_excerpt")
            or ""
        ).strip()
    employer_editor_key = f"resume_employer_text_v20_{teacher_identity}"
    if employer_editor_key not in st.session_state:
        st.session_state[employer_editor_key] = supplemental_default

    supplemental_employer_text = st.text_area(
        "完整雇主原文（可选，用于补充标准订单未保留的工作内容）",
        height=180,
        key=employer_editor_key,
        placeholder="可选。如果标准订单已经完整，可留空；如果想让AI看到更完整的工作内容，可粘贴原始雇主需求。",
    )

    st.markdown("### ④ 生成岗位定制简历")
    r1, r2 = st.columns([4, 1])
    with r1:
        generate_resume = st.button(
            "AI生成岗位定制简历",
            type="primary",
            use_container_width=True,
            key="resume_optimizer_generate_v20",
        )
    with r2:
        clear_resume_result = st.button(
            "清除定制结果",
            use_container_width=True,
            key="resume_optimizer_clear_result_v20",
        )

    if clear_resume_result:
        for key in [
            "resume_optimizer_result_v20",
            "resume_optimizer_model_v20",
            "resume_optimizer_result_teacher_v20",
            "resume_optimizer_result_order_v20",
            "resume_tailored_editor_v20",
            "resume_brief_editor_v225",
            "resume_recommendation_editor_v20",
        ]:
            st.session_state.pop(key, None)
        st.rerun()

    if generate_resume:
        if not parsed_target:
            st.warning("请先选择或解析目标订单。")
        else:
            try:
                with st.spinner("Gemini 正在基于真实老师资料和目标订单重组简历..."):
                    resume_result, resume_model = generate_tailored_resume(
                        teacher=resume_teacher,
                        parsed_order=parsed_target,
                        original_resume=original_resume_text,
                        supplemental_employer_text=supplemental_employer_text,
                    )
                    st.session_state["resume_optimizer_result_v20"] = resume_result
                    st.session_state["resume_optimizer_model_v20"] = resume_model
                    st.session_state["resume_optimizer_result_teacher_v20"] = teacher_name(resume_teacher)
                    st.session_state["resume_optimizer_result_order_v20"] = order_title(parsed_target, 1)
                    st.session_state["resume_tailored_editor_v20"] = str(
                        resume_result.get("tailored_resume_markdown") or ""
                    )
                    st.session_state["resume_brief_editor_v225"] = str(
                        resume_result.get("brief_resume_markdown") or ""
                    )
                    st.session_state["resume_recommendation_editor_v20"] = str(
                        resume_result.get("employer_recommendation") or ""
                    )
                st.rerun()
            except Exception as exc:
                render_api_error(exc)

    resume_result = st.session_state.get("resume_optimizer_result_v20")
    if resume_result:
        st.divider()
        result_teacher = st.session_state.get("resume_optimizer_result_teacher_v20") or teacher_name(resume_teacher)
        result_order = st.session_state.get("resume_optimizer_result_order_v20") or "目标订单"
        st.markdown(f"## {result_teacher}｜针对 {result_order} 的定制简历")
        st.success("此版本只允许使用原始简历和老师数据库中已有证据；缺少证据的要求不会被写成老师能力。")

        title = str(resume_result.get("resume_title") or "").strip()
        summary = str(resume_result.get("professional_summary") or "").strip()
        strengths = [str(x) for x in resume_result.get("core_strengths", []) if str(x).strip()]

        if title:
            st.markdown(f"### {title}")
        if summary:
            st.write(summary)
        if strengths:
            st.markdown("#### 本岗位重点优势")
            for strength in strengths:
                st.write(f"• {strength}")

        evidence = resume_evidence_rows(resume_result)
        st.markdown("### 岗位要求 ↔ 老师真实证据")
        if evidence:
            st.dataframe(evidence, use_container_width=True, hide_index=True)
        else:
            st.caption("AI未返回证据对照表，请人工复核定制简历。")

        questions = [str(x) for x in resume_result.get("questions_to_confirm", []) if str(x).strip()]
        notes = [str(x) for x in resume_result.get("factuality_notes", []) if str(x).strip()]
        if questions or notes:
            with st.expander("⚠️ 上户/投递前需要人工确认", expanded=True):
                for question in questions:
                    st.warning(question)
                for note in notes:
                    st.info(note)

        st.markdown("### 完整岗位定制版简历（可继续人工修改）")
        tailored_text = st.text_area(
            "定制简历",
            height=760,
            key="resume_tailored_editor_v20",
        )

        st.markdown("### 精简版简历（可继续人工修改）")
        st.caption(
            "精简版不是把完整版简单截断，而是同一次 Gemini 请求单独生成："
            "保留最相关的2-4段经历、最多4项核心优势，并明显压缩次要经历。"
        )
        brief_tailored_text = st.text_area(
            "精简版简历",
            height=480,
            key="resume_brief_editor_v225",
        )

        st.markdown("### 给派单老师 / 雇主的候选人推荐语")
        recommendation_text = st.text_area(
            "推荐简介",
            height=220,
            key="resume_recommendation_editor_v20",
        )

        deemphasized = [str(x) for x in resume_result.get("content_deemphasized", []) if str(x).strip()]
        if deemphasized:
            with st.expander("本岗位中被压缩/后置的真实内容"):
                for item in deemphasized:
                    st.write(f"• {item}")

        download_body = tailored_text.strip()
        if recommendation_text.strip():
            download_body += "\n\n【候选人推荐语】\n" + recommendation_text.strip()

        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "下载岗位定制简历 TXT",
                data=download_body.encode("utf-8"),
                file_name=f"{result_teacher}_岗位定制简历.txt".replace("/", "-"),
                mime="text/plain;charset=utf-8",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                "下载事实校验 JSON",
                data=json.dumps(resume_result, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name=f"{result_teacher}_简历事实校验.json".replace("/", "-"),
                mime="application/json",
                use_container_width=True,
            )

        st.markdown("### 生成专业简历 PDF")
        st.caption(
            "PDF采用中文单栏竖版。完整版保留更完整的相关工作经历；"
            "精简版使用独立生成的精简正文，不再与完整版重复。"
            "PDF会清理 **、__、多余星号、下划线、反引号等Markdown符号；"
            "不会显示匹配度、匹配原则、证据表、冲突或待确认分析。"
        )

        if not PDF_EXPORT_AVAILABLE:
            st.warning(
                "PDF功能当前未启用，因为 Streamlit 环境没有安装 PDF 依赖。"
                "请确认仓库根目录 requirements.txt 包含：reportlab、Pillow。"
            )
            if PDF_EXPORT_IMPORT_ERROR:
                st.caption(f"PDF依赖加载信息：{PDF_EXPORT_IMPORT_ERROR}")
        else:
            include_photo = st.checkbox(
                "PDF中包含老师照片",
                value=bool(teacher_photo_url(resume_teacher)),
                disabled=not bool(teacher_photo_url(resume_teacher)),
                key=f"resume_pdf_include_photo_v221_{teacher_identity}",
            )

            pdf_photo_bytes: Optional[bytes] = None
            if include_photo:
                try:
                    active_photo_url = teacher_photo_url(resume_teacher)
                    if active_photo_url:
                        pdf_photo_bytes = download_binary_url(active_photo_url)
                except Exception as exc:
                    st.warning(f"老师照片暂时无法下载，将生成无照片PDF：{exc}")
                    pdf_photo_bytes = None

            try:
                full_pdf = build_resume_pdf_bytes(
                    teacher_name_text=result_teacher,
                    resume_result=resume_result,
                    tailored_text=tailored_text,
                    recommendation_text=recommendation_text,
                    photo_bytes=pdf_photo_bytes,
                    mode="full",
                    teacher_profile=resume_teacher,
                )
                brief_pdf = build_resume_pdf_bytes(
                    teacher_name_text=result_teacher,
                    resume_result=resume_result,
                    tailored_text=brief_tailored_text,
                    recommendation_text=recommendation_text,
                    photo_bytes=pdf_photo_bytes,
                    mode="brief",
                    teacher_profile=resume_teacher,
                )

                p1, p2 = st.columns(2)
                with p1:
                    st.download_button(
                        "下载完整版简历 PDF",
                        data=full_pdf,
                        file_name=f"{result_teacher}_岗位定制简历.pdf".replace("/", "-"),
                        mime="application/pdf",
                        use_container_width=True,
                    )
                with p2:
                    st.download_button(
                        "下载精简版简历 PDF",
                        data=brief_pdf,
                        file_name=f"{result_teacher}_精简版简历.pdf".replace("/", "-"),
                        mime="application/pdf",
                        use_container_width=True,
                    )
            except Exception as exc:
                st.warning(f"PDF生成暂时失败：{exc}")


# ============================================================
# 16. MODE 5 - NEW TEACHER INTAKE
# ============================================================

else:
    st.markdown('<div class="section-title">新老师录入 → 保存到 Baserow</div>', unsafe_allow_html=True)
    st.caption(
        "把新老师完整简历粘贴进来，并可上传老师照片。Gemini 只负责把简历解析成当前 Teachers 表已有字段；"
        "你人工确认/修改后，程序才把数据真正写入 Baserow。Original Resume 保存原文，Teacher Photo 保存照片。"
    )

    try:
        intake_schema = load_baserow_fields()
        intake_field_map = {str(f.get("name")): f for f in intake_schema if f.get("name")}
    except Exception as exc:
        st.error("无法读取 Baserow Teachers 字段结构。")
        st.exception(exc)
        st.stop()

    required_storage_fields = []
    if "Original Resume" not in intake_field_map:
        required_storage_fields.append("Original Resume（Long text）")
    if "Teacher Photo" not in intake_field_map:
        required_storage_fields.append("Teacher Photo（File）")

    if required_storage_fields:
        st.warning(
            "为了完整使用新老师录入功能，建议在 Teachers 表新增："
            + "；".join(required_storage_fields)
            + "。没有这些字段也可以先保存其他结构化资料。"
        )
    else:
        st.success("✅ 已检测到 Original Resume 和 Teacher Photo 字段。")

    st.markdown("### ① 提供老师原始简历与照片")
    intake_resume = st.text_area(
        "老师完整原始简历",
        height=600,
        key="teacher_intake_resume_v22",
        placeholder=(
            "把老师完整简历原文粘贴到这里。\n"
            "系统会保留原文到 Original Resume，并另外解析学历、城市、语言、驾驶、住家、工作经验等结构化字段。"
        ),
    )

    intake_photo = st.file_uploader(
        "老师照片（可选，JPG / PNG / WEBP）",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=False,
        key="teacher_intake_photo_v22",
    )
    if intake_photo is not None:
        st.image(intake_photo, width=180, caption="待保存老师照片")

    i1, i2 = st.columns([4, 1])
    with i1:
        intake_parse = st.button(
            "① AI解析老师简历",
            type="primary",
            use_container_width=True,
            key="teacher_intake_parse_v22",
        )
    with i2:
        intake_clear = st.button(
            "清除录入内容",
            use_container_width=True,
            key="teacher_intake_clear_v22",
        )

    if intake_clear:
        for key in [
            "teacher_intake_resume_v22",
            "teacher_intake_parsed_v22",
            "teacher_intake_editor_v22",
            "teacher_intake_model_v22",
            "teacher_intake_saved_v22",
        ]:
            st.session_state.pop(key, None)
        st.rerun()

    if intake_parse:
        if not intake_resume.strip():
            st.warning("请先粘贴老师完整简历。")
        else:
            try:
                with st.spinner("Gemini 正在按当前 Baserow Teachers 字段解析老师简历..."):
                    parsed_teacher, model_used = parse_teacher_resume(intake_resume)
                st.session_state["teacher_intake_parsed_v22"] = parsed_teacher
                st.session_state["teacher_intake_model_v22"] = model_used
                st.session_state["teacher_intake_editor_v22"] = json.dumps(
                    parsed_teacher.get("teacher_data", {}),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            except Exception as exc:
                render_api_error(exc)

    parsed_teacher = st.session_state.get("teacher_intake_parsed_v22")
    if parsed_teacher:
        st.divider()
        st.markdown("### ② 人工检查 / 修改结构化老师资料")
        st.info(
            "下面 JSON 的字段名必须保持为 Baserow Teachers 中已有字段。"
            "Original Resume 不需要写在这里，保存时会自动使用上面的完整原文。"
        )

        intake_editor = st.text_area(
            "准备写入 Baserow 的老师字段（可修改）",
            height=650,
            key="teacher_intake_editor_v22",
        )

        parse_notes = [
            str(x) for x in parsed_teacher.get("parse_notes", [])
            if str(x).strip()
        ]
        if parse_notes:
            with st.expander("⚠️ AI解析后建议人工确认", expanded=True):
                for item in parse_notes:
                    st.warning(item)

        source_evidence = parsed_teacher.get("source_evidence", {})
        if isinstance(source_evidence, dict) and source_evidence:
            with st.expander("查看字段来源证据"):
                rows = [
                    {"字段": key, "简历证据": value}
                    for key, value in source_evidence.items()
                ]
                st.dataframe(rows, use_container_width=True, hide_index=True)

        try:
            edited_teacher_data = json.loads(intake_editor) if intake_editor.strip() else {}
            if not isinstance(edited_teacher_data, dict):
                raise ValueError("顶层必须是 JSON object。")

            preview_payload, preview_warnings = prepare_teacher_row_for_baserow(
                edited_teacher_data,
                intake_resume,
            )

            st.markdown("#### 保存预览")
            st.json(preview_payload, expanded=False)

            if preview_warnings:
                with st.expander("保存前提示", expanded=True):
                    for warning in preview_warnings:
                        st.warning(warning)

            st.markdown("### ③ 确认并保存到 Baserow")
            st.caption(
                "这一步不会再次调用 Gemini。点击后会新增一位老师；"
                "如果上传了照片，程序先上传文件，再把文件关联到 Teacher Photo 字段。"
            )

            save_teacher = st.button(
                "② 确认老师资料并保存到 Baserow",
                type="primary",
                use_container_width=True,
                key="teacher_intake_save_v22",
            )

            if save_teacher:
                try:
                    final_payload = dict(preview_payload)

                    if intake_photo is not None:
                        if "Teacher Photo" in intake_field_map:
                            uploaded = baserow_upload_file(
                                intake_photo.getvalue(),
                                intake_photo.name,
                                intake_photo.type,
                            )
                            final_payload["Teacher Photo"] = [{"name": uploaded["name"]}]
                        else:
                            st.warning(
                                "已选择照片，但 Teachers 表没有 Teacher Photo（File）字段，"
                                "本次不会保存照片。"
                            )

                    created = baserow_create_row(final_payload)
                    load_teachers.clear()
                    load_baserow_fields.clear()

                    saved_name = " ".join(
                        str(final_payload.get(key) or "").strip()
                        for key in ["First Name", "Last Name"]
                    ).strip()
                    if not saved_name:
                        saved_name = str(
                            final_payload.get("Chinese Name")
                            or final_payload.get("Name")
                            or "新老师"
                        )

                    st.session_state["teacher_intake_saved_v22"] = {
                        "row_id": created.get("id"),
                        "name": saved_name,
                    }
                    st.success(
                        f"✅ 已保存到 Baserow。老师：{saved_name}；"
                        f"Row ID：{created.get('id')}。"
                    )
                    st.info(
                        "老师已经进入数据库。点击侧边栏「刷新老师数据」后，"
                        "即可立即进行订单匹配、反向找订单和生成定制PDF简历。"
                    )
                except Exception as exc:
                    render_api_error(exc)

        except json.JSONDecodeError as exc:
            st.error(f"结构化老师 JSON 当前无法读取：{exc}")
        except Exception as exc:
            st.error(f"老师数据预览失败：{exc}")

    saved_teacher = st.session_state.get("teacher_intake_saved_v22")
    if saved_teacher:
        st.caption(
            f"最近保存：{saved_teacher.get('name')} "
            f"(Baserow Row ID {saved_teacher.get('row_id')})"
        )


# ============================================================
# 17. FOOTER
# ============================================================

st.divider()
st.caption(
    "Teacher Matching System V2.2.5 · AI统一订单格式、老师匹配、老师自动入库、照片管理、完整/精简岗位定制简历、PDF导出与事实校验。"
    "自动评分只使用岗位相关资格、能力、工作条件和明确的 OR/AND 组合条件；"
    "岗位定制简历只重组有来源证据的真实经历，个人属性要求不用于自动匹配或简历优化。"
)
