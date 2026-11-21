import json
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "## Best seller\n**Rice 5kg** leads revenue.\n\n- Beans next\n\n<script>alert(1)</script>"}}]}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
import sys, time
DELAY = float(sys.argv[2]) if len(sys.argv) > 2 else 0
_post = H.do_POST
def slow(self):
    time.sleep(DELAY); _post(self)
H.do_POST = slow
HTTPServer(('127.0.0.1', int(sys.argv[1]) if len(sys.argv) > 1 else 8799), H).serve_forever()
