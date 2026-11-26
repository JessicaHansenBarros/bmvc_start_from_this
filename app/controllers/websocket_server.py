import base64
import hashlib
import json
import socket
import struct
import threading
from http.cookies import SimpleCookie
from socketserver import ThreadingMixIn
from typing import Callable
from wsgiref.simple_server import ServerHandler, WSGIRequestHandler, WSGIServer

from bottle import ServerAdapter

WS_MAGIC_STRING = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_PAYLOAD_BYTES = 1024 * 1024  # 1 MiB


def _build_frame(opcode: int, payload: bytes) -> bytes:
    """Empacota um frame WebSocket (servidor -> cliente, sem máscara)."""
    length = len(payload)
    header = bytearray([0x80 | (opcode & 0x0F)])
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))
    return bytes(header) + payload


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    """Lê exatamente `size` bytes do socket ou retorna vazio no EOF."""
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = conn.recv(remaining)
        if not chunk:
            raise EOFError("Conexão WebSocket encerrada.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_frame(conn: socket.socket) -> tuple[bool, int, bytes]:
    """Lê um frame RFC 6455 completo enviado pelo cliente."""
    first, second = _recv_exact(conn, 2)
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F

    if length == 126:
        (length,) = struct.unpack("!H", _recv_exact(conn, 2))
    elif length == 127:
        (length,) = struct.unpack("!Q", _recv_exact(conn, 8))

    if length > MAX_PAYLOAD_BYTES:
        raise ValueError("Payload WebSocket excede o limite permitido.")

    mask_key = _recv_exact(conn, 4) if masked else b""
    payload = _recv_exact(conn, length) if length > 0 else b""

    if masked and payload:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    return fin, opcode, payload


class WebSocketClient:
    """Representa uma conexão WebSocket autenticada de um professor."""

    def __init__(self, conn: socket.socket, professor_id: int, session_id: str):
        self.conn = conn
        self.professor_id = professor_id
        self.session_id = session_id
        self._send_lock = threading.Lock()
        self._closed = False

    def send_text(self, text: str) -> bool:
        return self._send_raw(0x1, text.encode("utf-8"))

    def send_json(self, data: dict) -> bool:
        return self.send_text(json.dumps(data, ensure_ascii=False))

    def send_pong(self, payload: bytes = b"") -> bool:
        return self._send_raw(0xA, payload)

    def close(self, code: int = 1000) -> None:
        with self._send_lock:
            if self._closed:
                return
            self._closed = True
            try:
                self.conn.sendall(_build_frame(0x8, struct.pack("!H", code)))
            except OSError:
                pass
            try:
                self.conn.close()
            except OSError:
                pass

    def _send_raw(self, opcode: int, payload: bytes) -> bool:
        with self._send_lock:
            if self._closed:
                return False
            try:
                self.conn.sendall(_build_frame(opcode, payload))
                return True
            except OSError:
                self._closed = True
                return False


class WebSocketHub:
    """Gerencia clientes WebSocket ativos agrupados por professor."""

    def __init__(self):
        self._lock = threading.RLock()
        self._clients_by_professor: dict[int, set[WebSocketClient]] = {}

    def register(self, client: WebSocketClient) -> int:
        with self._lock:
            grupo = self._clients_by_professor.setdefault(client.professor_id, set())
            grupo.add(client)
            return len(grupo)

    def unregister(self, client: WebSocketClient) -> int:
        with self._lock:
            grupo = self._clients_by_professor.get(client.professor_id)
            if not grupo:
                return 0
            grupo.discard(client)
            restantes = len(grupo)
            if restantes == 0:
                self._clients_by_professor.pop(client.professor_id, None)
            return restantes

    def count_professor_clients(self, professor_id: int) -> int:
        with self._lock:
            return len(self._clients_by_professor.get(professor_id, set()))

    def broadcast_professor(
        self,
        professor_id: int,
        payload: dict,
        exclude: WebSocketClient | None = None,
    ) -> None:
        with self._lock:
            clientes = list(self._clients_by_professor.get(professor_id, set()))

        desconectados: list[WebSocketClient] = []
        for cliente in clientes:
            if exclude is not None and cliente is exclude:
                continue
            if not cliente.send_json(payload):
                desconectados.append(cliente)

        for cliente in desconectados:
            self.unregister(cliente)


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = True


def _extract_session_id(headers) -> str | None:
    raw_cookie = headers.get("Cookie")
    if not raw_cookie:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(raw_cookie)
    except Exception:
        return None
    morsel = cookie.get("session_id")
    return morsel.value if morsel else None


def make_websocket_request_handler(
    hub: WebSocketHub,
    resolve_session: Callable[[str | None], int | None],
    on_connect: Callable[[WebSocketClient], None] | None = None,
    on_message: Callable[[WebSocketClient, dict], None] | None = None,
    on_disconnect: Callable[[WebSocketClient], None] | None = None,
):
    """Cria uma subclasse de WSGIRequestHandler com suporte nativo a WebSocket em /ws."""

    class WebSocketWSGIRequestHandler(WSGIRequestHandler):
        def handle(self):
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                self.close_connection = True
                return
            if len(self.raw_requestline) > 65536:
                self.requestline = ""
                self.request_version = ""
                self.command = ""
                self.send_error(414)
                return

            if not self.parse_request():
                return

            upgrade_header = self.headers.get("Upgrade", "").lower()
            route_path = self.path.split("?", 1)[0]
            if upgrade_header == "websocket" and route_path == "/ws":
                self._handle_websocket()
                return

            handler = ServerHandler(
                self.rfile,
                self.wfile,
                self.get_stderr(),
                self.get_environ(),
                multithread=True,
            )
            handler.request_handler = self
            handler.run(self.server.get_app())

        def _handle_websocket(self):
            self.close_connection = True
            ws_key = self.headers.get("Sec-WebSocket-Key")
            if not ws_key:
                self.send_error(400, "Sec-WebSocket-Key ausente.")
                return

            session_id = _extract_session_id(self.headers)
            professor_id = resolve_session(session_id)
            if professor_id is None or not session_id:
                self.send_response(401, "Unauthorized")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            accept_raw = hashlib.sha1((ws_key.strip() + WS_MAGIC_STRING).encode("utf-8")).digest()
            accept_key = base64.b64encode(accept_raw).decode("ascii")

            handshake = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n"
                "\r\n"
            )
            self.wfile.write(handshake.encode("ascii"))
            self.wfile.flush()

            client = WebSocketClient(self.connection, professor_id=professor_id, session_id=session_id)
            hub.register(client)

            try:
                if on_connect:
                    on_connect(client)

                fragment_buffer = bytearray()
                while True:
                    fin, opcode, payload = _recv_frame(self.connection)

                    if opcode == 0x8:  # Close
                        break
                    if opcode == 0x9:  # Ping
                        client.send_pong(payload)
                        continue
                    if opcode == 0xA:  # Pong
                        continue

                    if opcode in (0x1, 0x0):
                        fragment_buffer.extend(payload)
                        if not fin:
                            continue
                        texto = fragment_buffer.decode("utf-8", errors="replace")
                        fragment_buffer.clear()
                        try:
                            dados = json.loads(texto)
                        except json.JSONDecodeError:
                            client.send_json({"type": "erro", "mensagem": "Mensagem JSON inválida."})
                            continue

                        if isinstance(dados, dict) and on_message:
                            on_message(client, dados)
            except (EOFError, OSError, ValueError):
                pass
            finally:
                hub.unregister(client)
                client.close()
                if on_disconnect:
                    on_disconnect(client)

    return WebSocketWSGIRequestHandler


class BottleWebSocketServer(ServerAdapter):
    """Adaptador Bottle com suporte a multi-threading e WebSocket nativo."""

    def __init__(
        self,
        host="0.0.0.0",
        port=8080,
        hub: WebSocketHub | None = None,
        resolve_session: Callable[[str | None], int | None] | None = None,
        on_connect: Callable[[WebSocketClient], None] | None = None,
        on_message: Callable[[WebSocketClient, dict], None] | None = None,
        on_disconnect: Callable[[WebSocketClient], None] | None = None,
        **options,
    ):
        super().__init__(host=host, port=port, **options)
        self.hub = hub or WebSocketHub()
        self.resolve_session = resolve_session or (lambda _sid: None)
        self.on_connect = on_connect
        self.on_message = on_message
        self.on_disconnect = on_disconnect

    def run(self, handler):
        from wsgiref.simple_server import make_server

        request_handler = make_websocket_request_handler(
            hub=self.hub,
            resolve_session=self.resolve_session,
            on_connect=self.on_connect,
            on_message=self.on_message,
            on_disconnect=self.on_disconnect,
        )
        server = make_server(
            self.host,
            self.port,
            handler,
            server_class=_ThreadingWSGIServer,
            handler_class=request_handler,
        )
        server.serve_forever()
