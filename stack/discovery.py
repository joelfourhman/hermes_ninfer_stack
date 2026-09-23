"""Use the resident server's model and context, never a client-side preset guess."""

from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.request


@dataclass(frozen=True)
class ServerModel:
    id: str
    context_length: int

    def client_values(self, values: dict[str, str]) -> dict[str, str]:
        return {
            **values,
            "NINFER_MODEL_ID": self.id,
            "NINFER_CONTEXT_LENGTH": str(self.context_length),
            "HERMES_COMPRESSION_THRESHOLD_TOKENS": str(min(
                int(values["HERMES_COMPRESSION_THRESHOLD_TOKENS"]),
                self.context_length // 2,
            )),
        }


def parse_model(payload: object, expected_id: str | None = None) -> ServerModel:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Expected exactly one resident NInfer model")
    row = rows[0]
    model_id, context = row.get("id"), row.get("max_model_len")
    if not isinstance(model_id, str) or not model_id or any(c.isspace() for c in model_id):
        raise ValueError("NInfer returned an invalid model ID")
    if expected_id is not None and model_id != expected_id:
        raise ValueError(f"NInfer advertises {model_id!r}, expected {expected_id!r}; refresh the client")
    if type(context) is not int or not 2048 <= context <= 262144:
        raise ValueError("NInfer must advertise a valid max_model_len; refusing to guess context")
    return ServerModel(model_id, context)


def discover(endpoint: str, api_key: str, expected_id: str | None = None) -> ServerModel:
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/models", headers={"Authorization": "Bearer " + api_key}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return parse_model(json.load(response), expected_id)
