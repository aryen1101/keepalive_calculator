"""
Test the calculator.
one TCP connection, every request on it, then check the socket is still open.

    python test.py               # requests one after another
    python test.py --pipelined   # all requests sent at once
"""
import socket
import sys

HOST, PORT = "localhost", 8080

CASES = [
    ("GET /add?a=2&b=3",   "GET /add?a=2&b=3 HTTP/1.1\r\nHost: localhost\r\n\r\n",  200, "5"),
    ("GET /sub?a=10&b=4",  "GET /sub?a=10&b=4 HTTP/1.1\r\nHost: localhost\r\n\r\n", 200, "6"),
    ("GET /mul?a=6&b=7",   "GET /mul?a=6&b=7 HTTP/1.1\r\nHost: localhost\r\n\r\n",  200, "42"),
    ("GET /div?a=9&b=3",   "GET /div?a=9&b=3 HTTP/1.1\r\nHost: localhost\r\n\r\n",  200, "3"),
    ("GET /div?a=1&b=0",   "GET /div?a=1&b=0 HTTP/1.1\r\nHost: localhost\r\n\r\n",  400, None),
    ("GET /add?a=x&b=3",   "GET /add?a=x&b=3 HTTP/1.1\r\nHost: localhost\r\n\r\n",  400, None),
    ("GET /pow?a=2&b=8",   "GET /pow?a=2&b=8 HTTP/1.1\r\nHost: localhost\r\n\r\n",  404, None),
    ("POST /add",          "POST /add HTTP/1.1\r\nHost: localhost\r\n\r\n",          405, None),
    ("GET /add (no Host)", "GET /add?a=2&b=3 HTTP/1.1\r\n\r\n",                     400, None),
]


def read_response(sock, buf):
    """Read one response using Content-Length. Returns (status, body, leftover)."""
    while b"\r\n\r\n" not in buf:
        buf += sock.recv(4096)
    head, body = buf.split(b"\r\n\r\n", 1)
    lines = head.decode().split("\r\n")
    status = int(lines[0].split()[1])
    length = 0
    for line in lines[1:]:
        if line.lower().startswith("content-length:"):
            length = int(line.split(":")[1])
    while len(body) < length:
        body += sock.recv(4096)
    return status, body[:length].decode(), body[length:]


def still_open(sock):
    sock.settimeout(0.3)
    try:
        return sock.recv(1, socket.MSG_PEEK) != b""   
    except socket.timeout:
        return True                                 


pipelined = "--pipelined" in sys.argv
sock = socket.create_connection((HOST, PORT))      
buf = b""
passed = True

if pipelined:
    sock.sendall("".join(raw for _, raw, _, _ in CASES).encode())

for label, raw, want_status, want_body in CASES:
    if not pipelined:
        sock.sendall(raw.encode())
    status, body, buf = read_response(sock, buf)
    ok = status == want_status and (want_body is None or body == want_body)
    passed &= ok
    print(f"{label:22} -> {status} {body if status == 200 else ''}{'' if ok else '   <-- expected ' + str(want_status)}")

open_ = still_open(sock)
passed &= open_
print(f"\nsocket still open: {open_}")
print(f"1 TCP handshake, {len(CASES)} responses")
print("\nRESULT:", "PASS" if passed else "FAIL")
sock.close()
sys.exit(0 if passed else 1)
