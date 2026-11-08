# ============================================================================
#  llm_client.py – Tích hợp LLM thông minh cho Chatbox Ao Nuôi
#  Hỗ trợ Google Gemini API và OpenAI API với Function Calling tự động
#  Sử dụng thư viện chuẩn urllib (không cần cài đặt thêm package ngoài)
# ============================================================================
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime

import chat_tools

logger = logging.getLogger(__name__)

# Các công cụ (Function Calling Schema) dành cho LLM
TOOLS_SCHEMA = [
    {
        "name": "get_current_status",
        "description": "Lấy thông tin trạng thái thời gian thực của ao nuôi: mực nước (%), khoảng cách cảm biến (cm), trạng thái 2 máy bơm (bơm cấp IN, bơm thoát OUT), chế độ (AUTO/MANUAL), kết nối ESP32 và cảm biến.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "get_level_change",
        "description": "Tính toán và phân tích biến động mực nước trong N phút qua (tăng/giảm bao nhiêu %, bao nhiêu cm, xu hướng biến động, min, max).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "minutes": {
                    "type": "INTEGER",
                    "description": "Khoảng thời gian cần phân tích tính bằng phút (mặc định 30 phút).",
                }
            },
        },
    },
    {
        "name": "get_day_summary",
        "description": "Tóm tắt tổng hợp hoạt động của ao nuôi trong ngày hôm nay hoặc 24 giờ qua: mức nước thấp nhất/cao nhất/trung bình, số lần bật từng bơm, thời gian bơm chạy, số lượng cảnh báo.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "hours": {
                    "type": "INTEGER",
                    "description": "Số giờ cần tổng kết (mặc định 24).",
                },
                "since_midnight": {
                    "type": "BOOLEAN",
                    "description": "True nếu chỉ tính từ 00:00 sáng hôm nay, False nếu tính 24 giờ qua.",
                },
            },
        },
    },
    {
        "name": "get_alerts",
        "description": "Tra cứu danh sách cảnh báo hoặc lỗi hệ thống gần đây trong bảng alerts.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "hours": {
                    "type": "INTEGER",
                    "description": "Số giờ tra cứu (mặc định 24 giờ).",
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Số lượng cảnh báo tối đa cần lấy (mặc định 5).",
                },
            },
        },
    },
    {
        "name": "get_config",
        "description": "Tra cứu các ngưỡng cài đặt mực nước bật/tắt bơm và giới hạn an toàn hiện tại của ao.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "propose_control",
        "description": "Tạo yêu cầu điều khiển máy bơm hoặc chế độ vận hành (cần người dùng xác nhận trước khi thực thi).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "Lệnh điều khiển: 'pump_in' (bơm cấp), 'pump_out' (bơm thoát), 'mode' (chế độ).",
                },
                "payload": {
                    "type": "STRING",
                    "description": "Giá trị lệnh: 'ON' hoặc 'OFF' cho bơm; 'AUTO' hoặc 'MANUAL' cho chế độ.",
                },
            },
            "required": ["command", "payload"],
        },
    },
]

SYSTEM_PROMPT = """Bạn là Trợ lý AI thông minh tích hợp trên website Giám sát & Điều khiển mực nước ao nuôi cá IoT.
Bạn có nhiệm vụ giải đáp thắc mắc, phân tích dữ liệu cảm biến thực tế và hỗ trợ điều khiển máy bơm một cách an toàn.

Nguyên tắc hoạt động:
1. Khi người dùng hỏi về tình trạng ao, mực nước, máy bơm, biến động, cảnh báo hay cấu hình: Hãy gọi tool tương ứng để lấy dữ liệu mới nhất từ hệ thống trước khi trả lời.
2. Trả lời bằng tiếng Việt thân thiện, súc tích, rõ ràng, định dạng số thập phân bằng dấu phẩy theo chuẩn Việt Nam (ví dụ 45,5 %).
3. Khi người dùng yêu cầu bật/tắt bơm hoặc chuyển chế độ: BẮT BUỘC phải gọi tool `propose_control` để tạo lệnh chờ xác nhận an toàn, không bao giờ khẳng định đã bật/tắt bơm trực tiếp khi chưa qua bước xác nhận!
4. Nếu người dùng chỉ chào hỏi, cảm ơn hoặc hỏi các câu trò chuyện thông thường: Hãy trả lời lịch sự và giới thiệu ngắn gọn các tính năng bạn có thể hỗ trợ về ao nuôi cá.
"""


def is_llm_available() -> bool:
    """Kiểm tra xem hệ thống đã được cấu hình API Key cho LLM hay chưa."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(gemini_key or openai_key)


def _execute_tool(tool_name: str, args: dict) -> dict:
    """Thực thi tool nghiệp vụ tương ứng và trả về kết quả dict."""
    logger.info(f"[LLM] Đang thực thi tool '{tool_name}' với args={args}")
    try:
        if tool_name == "get_current_status":
            return chat_tools.get_current_status()
        elif tool_name == "get_level_change":
            minutes = int(args.get("minutes", 30))
            return chat_tools.get_level_change(minutes=minutes)
        elif tool_name == "get_day_summary":
            hours = int(args.get("hours", 24))
            since_midnight = bool(args.get("since_midnight", True))
            return chat_tools.get_day_summary(hours=hours, since_midnight=since_midnight)
        elif tool_name == "get_alerts":
            hours = int(args.get("hours", 24))
            limit = int(args.get("limit", 5))
            return chat_tools.get_alerts(hours=hours, limit=limit)
        elif tool_name == "get_config":
            return chat_tools.get_config()
        elif tool_name == "propose_control":
            cmd = args.get("command", "")
            payload = args.get("payload", "")
            return chat_tools.propose_control(cmd, payload)
        else:
            return {"error": f"Tool không xác định: {tool_name}"}
    except Exception as e:
        logger.error(f"[LLM] Lỗi thực thi tool '{tool_name}': {e}", exc_info=True)
        return {"error": str(e)}


def call_gemini(user_message: str) -> dict | None:
    """Gọi Gemini REST API với function calling."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    # Định dạng schema functions cho Gemini
    gemini_tools = [
        {
            "function_declarations": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                }
                for t in TOOLS_SCHEMA
            ]
        }
    ]

    contents = [
        {"role": "user", "parts": [{"text": user_message}]}
    ]

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "tools": gemini_tools,
        "generationConfig": {"temperature": 0.2},
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        candidate = data.get("candidates", [{}])[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        # Kiểm tra nếu model gọi function call
        for part in parts:
            if "functionCall" in part:
                fc = part["functionCall"]
                fname = fc.get("name")
                fargs = fc.get("args", {})
                tool_result = _execute_tool(fname, fargs)

                # Nếu là propose_control, trả về trực tiếp card xác nhận
                if fname == "propose_control" and tool_result.get("success"):
                    import chat_router
                    return chat_router.handle_control(fargs.get("command"), fargs.get("payload"))

                # Gửi kết quả tool về cho Gemini để sinh câu trả lời tự nhiên
                contents.append(content)
                contents.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": fname,
                            "response": {"result": tool_result}
                        }
                    }]
                })

                payload["contents"] = contents
                req2 = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    data2 = json.loads(resp2.read().decode("utf-8"))

                candidate2 = data2.get("candidates", [{}])[0]
                text2 = ""
                for p in candidate2.get("content", {}).get("parts", []):
                    if "text" in p:
                        text2 += p["text"]

                now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
                return {
                    "handled": True,
                    "intent": fname,
                    "type": "llm",
                    "status_icon": "🤖",
                    "title": f"Phân tích AI cho câu hỏi của bạn:",
                    "description": text2,
                    "metrics": [],
                    "data_time": f"Phản hồi lúc {now_str}",
                }

            elif "text" in part:
                # Model trả lời trực tiếp mà không cần tool (ví dụ chào hỏi)
                now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
                return {
                    "handled": True,
                    "intent": "llm_direct",
                    "type": "llm",
                    "status_icon": "🤖",
                    "title": "Trợ lý AI phản hồi:",
                    "description": part["text"],
                    "metrics": [],
                    "data_time": f"Phản hồi lúc {now_str}",
                }

    except Exception as e:
        logger.warning(f"[LLM] Lỗi gọi Gemini API: {e}")
        return None

    return None

