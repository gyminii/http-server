# Python HTTP Server from Scratch

A minimal HTTP/1.0 server implementation in Python using raw sockets, built to understand networking fundamentals.

## Features

- **TCP Socket Programming** - Built from `socket` module without frameworks
- **HTTP Protocol Parsing** - Manual request/response handling
- **Content-Length Handling** - Properly reads variable-length request bodies across multiple TCP packets
- **MIME Type Detection** - Serves HTML, CSS, JS, images with correct content types
- **Query Parameters** - URL parameter parsing and routing
- **Thread Pool** - Concurrent connection handling with fixed thread pool (20 workers)
- **Request Timeout** - 10-second timeout to prevent resource exhaustion
- **Logging** - File and console logging for debugging

## Quick Start
```bash
# Clone the repository
git clone https://github.com/gyminii/http-server.git
cd python-http-server

# Run the server
python httpserver.py

# Server starts on http://localhost:8080
```

## Project Structure
```
python-http-server/
├── httpserver.py          # Main server implementation
├── htdocs/                # Static files directory
│   ├── index.html
│   ├── style.css
│   └── script.js
├── server.log             # Auto-generated log file
└── README.md
```

## Usage Examples

### GET Requests
```bash
# Home page
curl http://localhost:8080/

# Health check
curl http://localhost:8080/api/health

# Query parameters
curl "http://localhost:8080/api/users?limit=10&offset=20"

# Static files
curl http://localhost:8080/style.css
```

### POST Requests
```bash
curl -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'
```

### Other Methods
```bash
# PUT
curl -X PUT http://localhost:8080/api/users/1 -d "name=your-name"

# DELETE
curl -X DELETE http://localhost:8080/api/users/1

# PATCH
curl -X PATCH http://localhost:8080/api/users/1 -d "age=your-age"
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serves index.html |
| GET | `/api/health` | Health check endpoint |
| GET | `/api/users` | User list with query params |
| POST | `/api/echo` | Echoes request body |
| PUT | `/api/*` | Update resource |
| DELETE | `/api/*` | Delete resource |
| PATCH | `/api/*` | Partial update |

## Configuration

Edit `httpserver.py` to customize:
```python
SERVER_HOST = '0.0.0.0'  # Bind address
SERVER_PORT = 8080        # Port number
max_workers = 20          # Thread pool size
timeout = 10.0            # Request timeout (seconds)
```

## Technical Implementation

### Content-Length Handling
```python
# Reads headers until \r\n\r\n
# Then reads exactly Content-Length bytes
while b'\r\n\r\n' not in request_data:
    chunk = c_connection.recv(1024)
    request_data += chunk

content_length = int(headers.get('Content-Length', 0))
while len(body_bytes) < content_length:
    chunk = c_connection.recv(1024)
    body_bytes += chunk
```

### Thread Pool
```python
thread_pool = ThreadPoolExecutor(max_workers=20)
thread_pool.submit(handle_client, connection, address)
```

## Limitations

- HTTP/1.0 only (no keep-alive)
- No HTTPS support
- No chunked transfer encoding
- Basic error handling
- Not production-ready

## Performance

- **Concurrent connections**: ~1000 (limited by thread pool)
- **Request timeout**: 10 seconds
- **Thread pool size**: 20 workers

For comparison:
- Async servers (Node.js/FastAPI): 10000+ concurrent connections
- This server: 1000 concurrent connections

## Logging

Logs are written to both console and `server.log`:
```
2026-01-14 14:23:11,445 - INFO - New connection from ('127.0.0.1', 52341)
2026-01-14 14:23:11,446 - INFO - 127.0.0.1 - GET /api/users - Query: {'limit': '10'}
2026-01-14 14:23:11,447 - INFO - 127.0.0.1 - Request completed successfully
```

## Testing
```bash
# Single request
curl http://localhost:8080/

# Load test (requires Apache Bench)
ab -n 1000 -c 100 http://localhost:8080/

# Large body test
curl -X POST http://localhost:8080/api/echo \
  -d "$(head -c 5000 /dev/urandom | base64)"
```

## Why This Exists

Educational project to understand:
- TCP socket programming
- HTTP protocol mechanics
- Thread pool concurrency
- Network I/O fundamentals

Not intended for production use. Use FastAPI, Flask, or Node.js for real applications.

## License

MIT

## Author

Tyler Lee - [minii.dev](https://minii.dev)
