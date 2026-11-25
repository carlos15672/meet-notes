"""Small localhost client used by the floating meeting controls."""
import json
import urllib.error
import urllib.request

API_BASE = "http://127.0.0.1:8000"
LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ApiError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def request(method, path, payload=None, timeout=5):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    target = API_BASE + path
    try:
        with LOCAL_HTTP.open(urllib.request.Request(target, data=data, headers=headers, method=method),
                             timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc).get("detail")
        except (ValueError, AttributeError):
            detail = None
        raise ApiError(detail if isinstance(detail, str) else "No se pudo completar la operación.",
                       exc.code) from exc
    except (OSError, ValueError) as exc:
        raise ApiError("No se pudo conectar con meet-notes. Inicia el proyecto y vuelve a intentarlo.") from exc


def devices():
    return request("GET", "/api/en-vivo/dispositivos")


def sessions():
    return request("GET", "/api/en-vivo/sesiones")["items"]


def session(session_id):
    return request("GET", f"/api/en-vivo/sesiones/{session_id}")


def start(name, title, system_id=None, microphone_id=None):
    return request("POST", "/api/en-vivo/sesiones", {
        "userName": name, "title": title,
        "system_device_id": system_id, "microphone_device_id": microphone_id}, timeout=15)


def action(session_id, verb):
    if verb not in {"pausar", "reanudar", "marcar", "finalizar"}:
        raise ValueError("Acción desconocida.")
    return request("POST", f"/api/en-vivo/sesiones/{session_id}/{verb}", timeout=15)
