# keepalive_calculator

A small HTTP/1.1 calculator server written directly on a TCP socket. No framework, no HTTP library, Python 3 standard library only. It keeps the connection open, so a client can send any number of requests over a single TCP connection.

## Requirements
Python 3.8 or newer. Nothing to install.

## Run

Start the server:
```
python server.py            # listens on 0.0.0.0:8080
python server.py 9090       # any other port
```

### 1. Using the test script
With the server running, open a second terminal:
```
python test.py               # sends every request one after another on one connection
python test.py --pipelined   # sends all requests at once, expects answers in order
```
Expected output:
```
GET /add?a=2&b=3       -> 200 5
GET /sub?a=10&b=4      -> 200 6
GET /mul?a=6&b=7       -> 200 42
GET /div?a=9&b=3       -> 200 3
GET /div?a=1&b=0       -> 400
GET /add?a=x&b=3       -> 400
GET /pow?a=2&b=8       -> 404
POST /add              -> 405
GET /add (no Host)     -> 400

socket still open: True
1 TCP handshake, 9 responses

RESULT: PASS
```

### 2. From the terminal with curl
Several URLs in one command travel over one connection. Look for `Reusing existing http: connection` before the second and third requests; the server terminal shows the same client port on all three lines.

**macOS / Linux**
```
curl -v "http://localhost:8080/add?a=2&b=3" "http://localhost:8080/mul?a=6&b=7" "http://localhost:8080/sub?a=10&b=4"
```

**Windows PowerShell** (`curl` there is an alias for Invoke-WebRequest, so call the real binary as `curl.exe`)
```
curl.exe -v "http://localhost:8080/add?a=2&b=3" "http://localhost:8080/mul?a=6&b=7" "http://localhost:8080/sub?a=10&b=4"
```

Single requests (use `curl.exe` on PowerShell):
```
curl -i "http://localhost:8080/add?a=2&b=3"     # 200  5
curl -i "http://localhost:8080/div?a=1&b=0"     # 400
curl -i "http://localhost:8080/pow?a=2&b=8"     # 404
curl -i -X POST "http://localhost:8080/add"     # 405
```

## API
| Request | Response |
|---|---|
| `GET /add?a=N&b=N` | `200`, sum |
| `GET /sub?a=N&b=N` | `200`, difference |
| `GET /mul?a=N&b=N` | `200`, product |
| `GET /div?a=N&b=N` | `200`, quotient (`9/3` → `3`, `7/2` → `3.5`) |
| divide by zero, `a` or `b` missing or not an integer | `400` |
| unknown path | `404` |
| any method other than GET | `405` with `Allow: GET` |
| HTTP/1.1 request without a `Host` header | `400` |
| unparseable request | `400`, then the connection is closed |

Responses are `text/plain` and always carry `Content-Length`.

## How it works
- Each connection has its own byte buffer. `recv()` may return part of a request or several requests at once, so nothing is parsed straight from `recv()`.
- A request's headers end at the first blank line (`\r\n\r\n`). Its body is exactly `Content-Length` bytes. The server consumes exactly that many bytes; the next byte belongs to the next request.
- After answering, the buffer is parsed again before reading more, so a burst of requests is answered in order (pipelining).
- The connection closes only when the client closes it, sends `Connection: close`, uses HTTP/1.0, sends something unparseable, or stays idle for 30 seconds.
- Requests with `Transfer-Encoding` are refused with `400` so two ways of measuring the body can never disagree.
- Each connection runs in its own thread, so many clients can be connected at once.

## Files
- `server.py` – the server
- `test.py` – one-connection test
