import json
import logging
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote

# Basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

MAX_REQUEST_SIZE = 1024 * 1024  # 1MB request limit for now

def parse_query_params(path):
    """
    Extract query parameters from path
    Example: /api/users?limit=10&offset=20
    Returns: ('/api/users', {'limit': '10', 'offset': '20'})
    """
    if '?' not in path:
        return path, {}

    path_part, query_string = path.split('?', 1)
    params = {}

    # Split by & to get key=value pairs
    for pair in query_string.split('&'):
        if '=' in pair:
            key, value = pair.split('=', 1)
            params[unquote(key)] = unquote(value) if value else ''
        else:
            # Handle flags without values (e.g., ?debug)
            params[unquote(pair)] = ''

    return path_part, params


def parse_request(request):
    """
    Parse HTTP request into method, path, headers, body
    Sample request:
        POST /api/users HTTP/1.1\r\n
        Host: localhost:8080\r\n
        Content-Type: application/x-www-form-urlencoded\r\n
        Content-Length: 15\r\n
        \r\n
        name=Tyler&age=25
    """
    # Parsing each line
    lines = request.split("\r\n")
    request_line = lines[0].split()

    # Validate request line has 3 parts: METHOD PATH VERSION
    if len(request_line) != 3:
        raise ValueError(f"Invalid request line: expected 3 parts, got {len(request_line)}")

    method = request_line[0]
    path = request_line[1]
    version = request_line[2]

    # Validate HTTP method
    ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
    if method not in ALLOWED_METHODS:
        raise ValueError(f"Method not implemented: {method}")

    # Validate HTTP version
    if version not in ['HTTP/1.0', 'HTTP/1.1']:
        raise ValueError(f"Unsupported HTTP version: {version}")

    headers = {}
    body_start = 0

    # Parse headers
    for i in range(1, len(lines)):
        # Marking end of headers
        if lines[i] == "":
            body_start = i + 1
            break
        # Parsing headers
        if ":" in lines[i]:
            key, value = lines[i].split(': ', 1)
            headers[key] = value

    # Extracting body
    # If body_start > 0, there were headers and blank line
    # Otherwise no headers found, no body
    body = '\r\n'.join(lines[body_start:]) if body_start > 0 else ''

    return method, path, headers, body


def route(method, path, headers, body, query_params):
    """Route requests to appropriate handlers"""

    # Handle OPTIONS requests
    if method == "OPTIONS":
        allowed_methods = "GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS"
        response = 'HTTP/1.0 200 OK\r\n'
        response += f'Allow: {allowed_methods}\r\n'
        response += 'Content-Length: 0\r\n'
        response += 'Connection: close\r\n'
        response += '\r\n'
        return response.encode('utf-8')

    # For HEAD requests, process as GET but remember to strip body later
    request_method = method
    if method == "HEAD":
        method = "GET"

    # API endpoints
    if method == "GET" and path == "/api/users":
        limit = query_params.get('limit', '10')
        offset = query_params.get('offset', '0')
        return json_response({
            'users': [],
            'limit': limit,
            'offset': offset
        })

    if method == "GET" and path == "/api/health":
        return json_response({'status': "ok", 'code': 200})

    if method == 'POST' and path == '/api/echo':
        return json_response({'received': body, 'method': 'POST'})

    if method == 'PUT' and path.startswith('/api/'):
        return json_response({'message': 'Resource updated', 'method': 'PUT', 'path': path})

    if method == 'DELETE' and path.startswith('/api/'):
        return json_response({'message': 'Resource deleted', 'method': 'DELETE', 'path': path})

    if method == 'PATCH' and path.startswith('/api/'):
        return json_response({'message': 'Resource partially updated', 'method': 'PATCH', 'path': path})

    # Static file serving
    if method == "GET" and path in ["/", "/index.html"]:
        return serve_file('index.html')

    if method == "GET":
        filename = path.lstrip('/')
        return serve_file(filename)

    # Check for 405 - path exists but wrong method
    if path in ["/api/users", "/api/health"]:
        return error_response(405, 'Method Not Allowed', extra_headers='Allow: GET, HEAD, OPTIONS\r\n')

    if path == '/api/echo':
        return error_response(405, 'Method Not Allowed', extra_headers='Allow: POST, OPTIONS\r\n')

    # No matching route found
    return error_response(404, 'Not Found')


def get_content_type(filename):
    """Determine MIME type based on file extension"""
    if filename.endswith('.html'):
        return 'text/html'
    elif filename.endswith('.css'):
        return 'text/css'
    elif filename.endswith('.js'):
        return 'application/javascript'
    elif filename.endswith('.json'):
        return 'application/json'
    elif filename.endswith('.png'):
        return 'image/png'
    elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
        return 'image/jpeg'
    elif filename.endswith('.gif'):
        return 'image/gif'
    else:
        return 'application/octet-stream'  # Generic binary


def serve_file(filename):
    """Serve static files from htdocs directory"""

    # URL decode the filename
    filename = unquote(filename)

    # Validate after decoding (prevent path traversal)
    if '..' in filename:
        return error_response(403, 'Forbidden')

    # Normalize paths and prevent directory traversal
    base_directory = os.path.abspath("htdocs")
    requested_path = os.path.abspath(os.path.join('htdocs', filename))

    if not (requested_path == base_directory or requested_path.startswith(base_directory + os.sep)):
        return error_response(403, 'Forbidden')

    # Images need to be read as binary, text files as text
    is_binary = filename.endswith(('.png', '.jpg', '.jpeg', '.gif'))
    mode = 'rb' if is_binary else 'r'

    try:
        with open(requested_path, mode) as file:
            content = file.read()
    except FileNotFoundError:
        return error_response(404, 'File Not Found')
    except PermissionError:
        return error_response(403, 'Forbidden')
    except Exception as e:
        logger.error(f"Error reading file {filename}: {str(e)}")
        return error_response(500, 'Internal Server Error')

    content_type = get_content_type(filename)

    # Calculate correct content length for UTF-8
    if is_binary:
        content_length = len(content)
    else:
        content_length = len(content.encode('utf-8'))

    # Build response headers
    response = 'HTTP/1.0 200 OK\r\n'
    response += f'Content-Type: {content_type}\r\n'
    response += f'Content-Length: {content_length}\r\n'
    response += 'Connection: close\r\n'
    response += '\r\n'

    # Encode response
    if is_binary:
        return response.encode('utf-8') + content
    else:
        return (response + content).encode('utf-8')


def json_response(data):
    """Build JSON response"""
    json_body = json.dumps(data)

    response = 'HTTP/1.0 200 OK\r\n'
    response += 'Content-Type: application/json\r\n'
    response += f'Content-Length: {len(json_body)}\r\n'
    response += 'Connection: close\r\n'
    response += '\r\n'
    response += json_body

    return response.encode('utf-8')


def error_response(status_code, message, extra_headers=''):
    """Build error response"""
    response = f"HTTP/1.0 {status_code} {message}\r\n"
    response += 'Content-Type: text/plain\r\n'
    response += f'Content-Length: {len(message)}\r\n'
    response += extra_headers
    response += 'Connection: close\r\n'
    response += '\r\n'
    response += message

    return response.encode('utf-8')


def handle_client(c_connection, c_address):
    """Handle a single client connection"""
    try:
        c_connection.settimeout(10.0)

        # Keep reading until we have the complete headers
        # Headers end with \r\n\r\n (blank line)
        request_data = b''
        while b'\r\n\r\n' not in request_data:
            # Prevent memory exhaustion attacks
            if len(request_data) > MAX_REQUEST_SIZE:
                c_connection.sendall(error_response(413, 'Request Too Large'))
                return

            chunk = c_connection.recv(1024)
            if not chunk:
                # Client disconnected before sending complete headers
                return
            request_data += chunk

        # Split the headers from any body data that already arrived
        # Sometimes the body comes in the same packet as headers
        header_end = request_data.index(b'\r\n\r\n')
        headers_part = request_data[:header_end].decode()
        body_bytes = request_data[header_end + 4:]  # +4 to skip the \r\n\r\n

        # Parse headers to find out how much body to expect
        method, path, headers, _ = parse_request(headers_part + '\r\n\r\n')

        # Parse query parameters
        path, query_params = parse_query_params(path)

        content_length = int(headers.get('Content-Length', 0))

        # Keep reading until we have all the body bytes
        # body_bytes might already have some data from the first recv()
        while len(body_bytes) < content_length:
            chunk = c_connection.recv(1024)
            if not chunk:
                # Connection closed before we got all the data
                break
            body_bytes += chunk

        # Convert bytes to string
        body = body_bytes.decode() if body_bytes else ''

        # Reconstruct query string for logging
        query_string = ''
        if query_params:
            query_string = '?' + '&'.join(f'{k}={v}' if v else k for k, v in query_params.items())

        logger.info(f"{c_address[0]} - {method} {path}{query_string}")

        # Store original method for HEAD handling
        original_method = method

        # Route to appropriate handler
        response = route(method, path, headers, body, query_params)

        # If HEAD request, strip body but keep headers
        if original_method == "HEAD":
            response_parts = response.split(b'\r\n\r\n', 1)
            response = response_parts[0] + b'\r\n\r\n'

        # Ensure response is bytes
        if isinstance(response, str):
            response = response.encode('utf-8')

        # Send response back
        c_connection.sendall(response)

        try:
            c_connection.shutdown(socket.SHUT_WR)
        except OSError:
            pass  # Connection already closed

        logger.info(f"{c_address[0]} - Request completed successfully")

    except ValueError as e:
        # Malformed request
        logger.error(f"{c_address[0]} - Malformed request: {str(e)}")
        response = error_response(400, 'Bad Request')
        c_connection.sendall(response)
        return
    except socket.timeout:
        logger.warning(f"{c_address[0]} - Connection timed out")
        return
    except Exception as e:
        logger.error(f"{c_address[0]} - Error: {str(e)}", exc_info=True)
        try:
            response = error_response(500, 'Internal Server Error')
            c_connection.sendall(response)
        except:
            pass  # Connection might be dead
        return
    finally:
        c_connection.close()


# Define socket host and port
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 8080

"""
AF_INET = IPv4
SOCK_STREAM = TCP Protocol
"""
# Create TCP socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Socket options
# Setting TCP Socket to bind to a port that is in wait time
# Without it, I would have to wait 60s+ before reusing ports
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# Attaching socket to host and port
# Calling bind lets you specify port and ip address
server_socket.bind((SERVER_HOST, SERVER_PORT))
server_socket.listen(5)
print('Listening on port %s ...' % SERVER_PORT)

# Thread pool
WORKERS = 20
thread_pool = ThreadPoolExecutor(max_workers=WORKERS)

try:
    while True:
        # Wait for client connections
        client_connection, client_address = server_socket.accept()
        logger.info(f"New connection from {client_address}")

        # Submit connection to thread pool instead of creating new thread
        # If all 20 threads are busy, this waits until one becomes free
        thread_pool.submit(handle_client, client_connection, client_address)

except KeyboardInterrupt:
    logger.info("Shutting down server...")
    thread_pool.shutdown(wait=True)
    server_socket.close()