"""
Mock tool environment: simulates email, refund, booking, code, medical-office tools.
All tools return structured results and track whether they were executed.
Irreversible tools are flagged so the action-safety guard can intercept them.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import uuid
import time


IRREVERSIBLE_TOOLS = {
    "send_email", "process_refund", "book_hotel",
    "book_flight", "submit_form", "cancel_booking",
    "delete_record", "publish_post",
}


@dataclass
class ToolCall:
    tool: str
    args: dict
    result: dict
    is_irreversible: bool
    executed_at: float = field(default_factory=time.time)
    call_id: str = field(default_factory=lambda: f"tc_{uuid.uuid4().hex[:6]}")


class MockToolEnvironment:
    def __init__(self):
        self.execution_log: list[ToolCall] = []
        self._inject_errors: dict[str, dict] = {}  # tool -> forced error result

    def inject_error(self, tool: str, error_result: dict) -> None:
        """Force a specific (possibly wrong) result for a tool — used in S1 cases."""
        self._inject_errors[tool] = error_result

    def clear_error(self, tool: str) -> None:
        self._inject_errors.pop(tool, None)

    def call(self, tool: str, args: dict) -> dict:
        if tool in self._inject_errors:
            result = dict(self._inject_errors[tool])
            result["_injected_error"] = True
        else:
            result = self._dispatch(tool, args)
        tc = ToolCall(
            tool=tool,
            args=args,
            result=result,
            is_irreversible=tool in IRREVERSIBLE_TOOLS,
        )
        self.execution_log.append(tc)
        return result

    def executed_irreversible(self) -> list[ToolCall]:
        return [tc for tc in self.execution_log if tc.is_irreversible]

    def reset(self) -> None:
        self.execution_log.clear()
        self._inject_errors.clear()

    def _dispatch(self, tool: str, args: dict) -> dict:
        handlers = {
            "send_email": self._send_email,
            "process_refund": self._process_refund,
            "book_hotel": self._book_hotel,
            "book_flight": self._book_flight,
            "check_flight_status": self._check_flight_status,
            "lookup_user_profile": self._lookup_user_profile,
            "search_knowledge_base": self._search_kb,
            "submit_form": self._submit_form,
            "cancel_booking": self._cancel_booking,
            "get_booking": self._get_booking,
            "update_profile": self._update_profile,
        }
        handler = handlers.get(tool)
        if handler:
            return handler(args)
        return {"status": "ok", "tool": tool, "mock": True}

    def _send_email(self, args: dict) -> dict:
        return {"status": "sent", "to": args.get("to"), "subject": args.get("subject"), "id": uuid.uuid4().hex[:8]}

    def _process_refund(self, args: dict) -> dict:
        return {"status": "processed", "amount": args.get("amount"), "order_id": args.get("order_id")}

    def _book_hotel(self, args: dict) -> dict:
        return {"status": "booked", "city": args.get("city"), "booking_id": f"H{uuid.uuid4().hex[:6]}"}

    def _book_flight(self, args: dict) -> dict:
        return {"status": "booked", "from": args.get("from"), "to": args.get("to"),
                "flight_id": f"F{uuid.uuid4().hex[:6]}"}

    def _check_flight_status(self, args: dict) -> dict:
        return {"status": "on_time", "flight": args.get("flight_id"), "gate": "B12"}

    def _lookup_user_profile(self, args: dict) -> dict:
        return {"user_id": args.get("user_id"), "name": "Alice", "email": "alice@example.com"}

    def _search_kb(self, args: dict) -> dict:
        return {"results": [{"text": "mock knowledge base result", "score": 0.9}]}

    def _submit_form(self, args: dict) -> dict:
        return {"status": "submitted", "form_id": args.get("form_id"), "ref": uuid.uuid4().hex[:8]}

    def _cancel_booking(self, args: dict) -> dict:
        return {"status": "cancelled", "booking_id": args.get("booking_id")}

    def _get_booking(self, args: dict) -> dict:
        return {"booking_id": args.get("booking_id"), "status": "confirmed", "city": "Boston"}

    def _update_profile(self, args: dict) -> dict:
        return {"status": "updated", "user_id": args.get("user_id"), "field": args.get("field")}
