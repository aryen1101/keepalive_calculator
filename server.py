#!/usr/bin/env python3
"""HTTP/1.1 calculator server on a raw TCP socket.
"""

import socket
import sys
import threading

HOST = "0.0.0.0"                                   # every interface
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
IDLE_TIMEOUT = 30                                  # seconds a silent client may stay connected
MAX_HEADER_BYTES = 64 * 1024                       # refuse absurd header blocks

REASON = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}


# calculator

def div(a, b):
    if b == 0:
        raise ValueError("division by zero")
    return a // b if a % b == 0 else a / b   


OPERATIONS = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mul": lambda a, b: a * b,
    "div": div,
}


def to_int(text):
    """Accept an optional sign and digits only; anything else is a 400."""
    digits = text.strip().lstrip("+-")
    if not digits.isdigit():
        raise ValueError(f"not an integer: {text!r}")
    return int(text)


# responses

def build_response(status, body, close=False):
    """Serialise one HTTP/1.1 response.

    Content-Length is always present so the client can find the end of the
    body without us closing the socket. Lines end in CRLF and the blank
    line separates headers from body.
    """
    data = body.encode()
    head = (
        f"HTTP/1.1 {status} {REASON[status]}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(data)}\r\n"
        f"Connection: {'close' if close else 'keep-alive'}\r\n"
        + ("Allow: GET\r\n" if status == 405 else "")
        + "\r\n"
    )
    return head.encode() + data


# parsing

def parse_request(buf):
    """Cut one complete request off the front of the byte buffer.

    Returns (request, bytes_used), or (None, 0) if the buffer does not yet
    hold a whole request. Raises ValueError if the bytes are not valid HTTP.

    Framing: the header block ends at the first blank line (a delimiter);
    the body is exactly Content-Length bytes (a length prefix). We take
    exactly that many bytes and no more. Byte n+1 belongs to the next request.
    """
    end = buf.find(b"\r\n\r\n")
    if end == -1:
        if len(buf) > MAX_HEADER_BYTES:
            raise ValueError("headers too large")
        return None, 0                                

    lines = buf[:end].decode("iso-8859-1").split("\r\n")
    parts = lines[0].split(" ")                      
    if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
        raise ValueError("bad request line")

    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if not sep:
            raise ValueError("bad header line")
        headers[name.strip().lower()] = value.strip()     

    if "transfer-encoding" in headers:
        raise ValueError("chunked requests not supported")
    length = int(headers.get("content-length", "0"))
    body_start = end + 4
    if len(buf) < body_start + length:
        return None, 0                                  

    request = {
        "method": parts[0],
        "target": parts[1],
        "version": parts[2],
        "headers": headers,
        "body": buf[body_start:body_start + length],
    }
    return request, body_start + length


#routing

def handle(request):
    """Decide the answer for one request. Returns (status, body_text)."""
    if request["version"] == "HTTP/1.1" and "host" not in request["headers"]:
        return 400, "missing Host header"
    if request["method"] != "GET":
        return 405, "only GET is allowed"

    path, _, query = request["target"].partition("?")
    operation = OPERATIONS.get(path.strip("/"))
    if operation is None:
        return 404, "unknown operation; use add, sub, mul, div"

    params = dict(p.split("=", 1) if "=" in p else (p, "") for p in query.split("&") if p)
    try:
        result = operation(to_int(params["a"]), to_int(params["b"]))
    except KeyError as e:
        return 400, f"missing parameter {e.args[0]}"
    except ValueError as e:                               
        return 400, str(e)
    return 200, str(result)


# connection

def serve_connection(conn, peer):
    """Serve one client until it leaves, asks to close, misbehaves or goes idle.

    A single byte buffer collects everything the client sends. recv() may
    deliver half a request or several at once, so nothing is parsed straight
    from recv(); the buffer is re-parsed before every read. That is also
    what makes pipelining work: a burst of requests is answered in order.
    """
    conn.settimeout(IDLE_TIMEOUT)
    buf = b""
    try:
        while True:
            while True:
                try:
                    request, used = parse_request(buf)
                except ValueError as e:
                    conn.sendall(build_response(400, f"malformed request: {e}", close=True))
                    return
                if request is None:
                    break
                buf = buf[used:]

                status, body = handle(request)
                close = (request["headers"].get("connection", "").lower() == "close"
                         or request["version"] == "HTTP/1.0")
                conn.sendall(build_response(status, body, close))
                print(f"[{peer[0]}:{peer[1]}] {request['method']} {request['target']} -> {status}", flush=True)
                if close:
                    return

            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                return                                    
            if not chunk:
                return                                 
            buf += chunk
    except (ConnectionResetError, BrokenPipeError):
        pass                                              
    finally:
        conn.close()


#  main

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow an immediate restart while the old socket is still in TIME_WAIT.
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(16)
    print(f"listening on {HOST}:{PORT}", flush=True)
    try:
        while True:
            conn, peer = server.accept()
            # One thread per connection so accept() is never blocked by a busy client.
            threading.Thread(target=serve_connection, args=(conn, peer), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


if __name__ == "__main__":
    main()
