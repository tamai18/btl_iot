# ============================================================================
#  chat.py – Flask Blueprint cho Chatbox AI Ao Nuôi
#  Hỗ trợ cả Fast Path NLP và LLM Function Calling thông minh
# ============================================================================
import logging
from flask import Blueprint, jsonify, request
import chat_router
import llm_client

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.route("", methods=["POST"])
def post_chat():
    """
    Nhận tin nhắn của người dùng và trả về phản hồi:
    1. Nếu có cấu hình LLM (Gemini API) -> Gọi LLM Function Calling.
    2. Nếu không có LLM hoặc LLM lỗi -> Dùng Fast Path NLP Engine.
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    try:
        # Nếu đã cấu hình LLM API Key thì ưu tiên gọi LLM
        if llm_client.is_llm_available():
            llm_res = llm_client.call_gemini(message)
            if llm_res and llm_res.get("handled"):
                return jsonify({"ok": True, "data": llm_res})
            else:
                logger.warning("[Chat API] LLM gặp sự cố (hết hạn mức/mất mạng), tự động chuyển về Tầng 1 (Fast Path)")
                result = chat_router.route_intent(message)
                result["description"] = (
                    "⚠️ [Chuyển về Tầng 1 - Fast Path] Dịch vụ AI (LLM) tạm thời không khả dụng (hết hạn mức hoặc mất kết nối Internet), hệ thống tự động chuyển về xử lý bằng dữ liệu cục bộ:\n\n"
                    + result.get("description", "")
                )
                return jsonify({"ok": True, "data": result})

        # Mặc định sử dụng Fast Path NLP Engine
        result = chat_router.route_intent(message)
        return jsonify({"ok": True, "data": result})

    except Exception as e:
        logger.error(f"[Chat API] Lỗi xử lý tin nhắn: {e}", exc_info=True)
        return jsonify({
            "ok": False,
            "error": str(e),
            "data": {
                "handled": False,
                "title": "❌ Lỗi hệ thống",
                "description": f"Đã xảy ra lỗi khi xử lý câu hỏi: {e}",
                "metrics": [],
            }
        }), 500


@chat_bp.route("/confirm", methods=["POST"])
def post_confirm():
    """
    Xác nhận lệnh điều khiển đang chờ.
    Body JSON: {"action_id": "..."} (tùy chọn)
    """
    data = request.get_json(silent=True) or {}
    action_id = data.get("action_id")

    try:
        result = chat_router.handle_confirm_action(action_id)
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        logger.error(f"[Chat API] Lỗi xác nhận lệnh: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@chat_bp.route("/cancel", methods=["POST"])
def post_cancel():
    """
    Hủy lệnh điều khiển đang chờ.
    Body JSON: {"action_id": "..."} (tùy chọn)
    """
    data = request.get_json(silent=True) or {}
    action_id = data.get("action_id")

    try:
        result = chat_router.handle_cancel_action(action_id)
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        logger.error(f"[Chat API] Lỗi hủy lệnh: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@chat_bp.route("/health", methods=["GET"])
def get_health():
    """Kiểm tra tình trạng dịch vụ Chatbox."""
    return jsonify({
        "ok": True,
        "service": "chatbox_ai",
        "fast_path": True,
        "llm_enabled": llm_client.is_llm_available(),
        "status": "ready"
    })
