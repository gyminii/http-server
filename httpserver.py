import threading
import socket
from concurrent.futures import ThreadPoolExecutor
import logging

# Basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log'),  # Write to file
        logging.StreamHandler()  # Also print to console
    ]
)

logger = logging.getLogger(__name__)

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
            params[key] = value

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
    # methods
    method = request_line[0]
    path = request_line[1]

    headers = {}
    body_start = 0

    for i in range(1, len(lines)):
        # marking end of headers
        if lines[i] == "":
            body_start = i + 1
            break
        # parsing headers
        if ":" in lines[i]:
            key, value = lines[i].split(': ', 1)
            headers[key] = value
    # Extracting body
    # If body_start > 0, there were headers and blank line
    # Otherwise no headers found, no body
    body = '\r\n'.join(lines[body_start:]) if body_start > 0 else ''

    return method, path, headers, body

def route(method, path, headers, body,query_params):

    if method == "GET" and path == "/api/users":
        limit = query_params.get('limit', '10')
        offset = query_params.get('offset', '0')
        return json_response({
            'users': [],
            'limit': limit,
            'offset': offset
        })

    # GET req for home
    if method == "GET" and path in ["/", "/index.html"]:
        return serve_file('index.html')

    # GET health checkpoint
    if method == "GET" and path == "/api/health":
        return json_response({'status': "ok", 'code': 200})

    # GET for static files
    if method == "GET":
        filename = path.lstrip('/')
        return serve_file(filename)

    # POST request to echo endpoint
    if method == 'POST' and path == '/api/echo':
        return json_response({'received': body, 'method': 'POST'})

    # PUT request - update resource
    if method == 'PUT' and path.startswith('/api/'):
        return json_response({'message': 'Resource updated', 'method': 'PUT', 'path': path})

    # DELETE request
    if method == 'DELETE' and path.startswith('/api/'):
        return json_response({'message': 'Resource deleted', 'method': 'DELETE', 'path': path})

    # PATCH request - partial update
    if method == 'PATCH' and path.startswith('/api/'):
        return json_response({'message': 'Resource partially updated', 'method': 'PATCH', 'path': path})

    # No matching route found
    return error_response(404, 'Not Found')

# Helper function to get the content types
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
    filepath = f'htdocs/{filename}'

    # Images need to be read as binary, text files as text
    is_binary = filename.endswith(('.png', '.jpg', '.jpeg', '.gif'))
    mode = 'rb' if is_binary else 'r'

    try:
        with open(filepath, mode) as file:
            content = file.read()
    except FileNotFoundError:
        return error_response(404, 'File Not Found')

    content_type = get_content_type(filename)

    # Build response headers
    response = 'HTTP/1.0 200 OK\r\n'
    response += f'Content-Type: {content_type}\r\n'
    response += 'Connection: close\r\n'
    response += '\r\n'

    # If binary file, return bytes. Otherwise, return string
    if is_binary:
        return response.encode() + content
    else:
        return response + content

def json_response(data):
    import json

    json_body = json.dumps(data)

    response = 'HTTP/1.0 200 OK\r\n'
    response += 'Content-Type: application/json\r\n'
    response += 'Connection: close\r\n'
    response += '\r\n'
    response += json_body

    return response

def error_response(status_code, message):
    response = f"HTTP/1.0 {status_code} {message}\r\n"
    response += 'Content-Type: text/plain\r\n'
    response += 'Connection: close\r\n'
    response += '\r\n'
    response += message

    return response


def handle_client(c_connection, c_address):
    """Handle a single client connection"""
    try:

        c_connection.settimeout(10.0)

        # Keep reading until we have the complete headers
        # Headers end with \r\n\r\n (blank line)
        request_data = b''
        while b'\r\n\r\n' not in request_data:
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

        # Logging the request
        logger.info(f"{c_address[0]} - {method} {path} - Query: {query_params}")

        # Route to appropriate handler
        response = route(method, path, headers, body, query_params)

        # Send response back
        c_connection.sendall(response.encode())
        c_connection.shutdown(socket.SHUT_WR)

        logger.info(f"{c_address[0]} - Request completed successfully")


    except socket.timeout:
        logger.warning(f"{c_address[0]} - Connection timed out")
        return
    except Exception as e:
        logger.error(f"{c_address[0]} - Error: {str(e)}", exc_info=True)
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
# Create TCPsocket
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

# thread pool
WORKERS=20
thread_pool = ThreadPoolExecutor(max_workers=WORKERS)

try:
    while True:
        # Wait for client connections
        client_connection, client_address = server_socket.accept()
        logger.info(f"New connection from {client_address}")

        # Submit connection to thread pool instead of creating new thread
        # If all 20 threads are busy, this waits until one becomes free
        #
        thread_pool.submit(handle_client, client_connection, client_address)

except KeyboardInterrupt:
    logger.info("Shutting down server...")
    thread_pool.shutdown(wait=True)
    server_socket.close()