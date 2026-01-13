import threading
import socket

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


def handle_request(request):
    """Handles the HTTP request."""

    headers = request.split('\n')
    filename = headers[0].split()[1]
    if filename == '/':
        filename = '/index.html'

    try:
        fin = open('htdocs' + filename)
        content = fin.read()
        fin.close()

        # response = 'HTTP/1.0 200 OK\n\n' + content
        response = 'HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n' + content
    except FileNotFoundError:
        response = 'HTTP/1.0 404 NOT FOUND\n\nFile Not Found'

    return response

def route(method, path, headers, body):
    """
    Route HTTP request to appropriate handler based on method and path
    """
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

    # No matching route found
    return error_response(404, 'Not Found')

def serve_file(filename):
    """
    Read file from htdocs directory and return as HTTP response
    Returns 404 if file doesn't exist
    """
    filepath = f'htdocs/{filename}'

    try:
        with open(filepath, 'r') as file:
            content = file.read()
    except FileNotFoundError:
        return error_response(404, 'File Not Found')

    # Build HTTP response with proper headers
    response = 'HTTP/1.0 200 OK\r\n'
    response += 'Content-Type: text/html\r\n'
    response += 'Connection: close\r\n'
    response += '\r\n'
    response += content

    return response

def json_response(data):
    """
    Convert Python dictionary to JSON and return as HTTP response
    """
    import json

    json_body = json.dumps(data)

    response = 'HTTP/1.0 200 OK\r\n'
    response += 'Content-Type: application/json\r\n'
    response += 'Connection: close\r\n'
    response += '\r\n'
    response += json_body

    return response

def error_response(status_code, message):
    """
    Return an HTTP error response with given status code and message
    """
    response = f"HTTP/1.0 {status_code} {message}\r\n"
    response += 'Content-Type: text/plain\r\n'
    response += 'Connection: close\r\n'
    response += '\r\n'
    response += message

    return response

def handle_client(c_connection, c_address):
    """Handle a single client connection"""
    try:
        request = c_connection.recv(1024).decode()
        print(f"Request from {c_address}:\n{request}")
        # Parse request
        method, path, headers, body = parse_request(request)
        print(f"Method: {method}, Path: {path}")
        # print(f"Headers: {headers}")
        # if body:
        #     print(f"Body: {body}\n")
        # Routing ot appropriate handler
        response = route(method, path, headers, body)
        # Sending response back
        c_connection.sendall(response.encode())
        c_connection.shutdown(socket.SHUT_WR)
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



try:
    while True:
        # Wait for client connections
        client_connection, client_address = server_socket.accept()
        print(f"Connection from {client_address}")

        # Concurrency
        thread = threading.Thread(
            target=handle_client,
            args=(client_connection, client_address)
        )
        thread.daemon = True
        thread.start()

except KeyboardInterrupt:
    print("\nShutting down...")
    server_socket.close()


