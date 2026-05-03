"""Reddit login via local HTTP server + real browser.

Instead of launching an automated browser (blocked by Reddit bot detection),
this approach:

1. Starts a temporary local HTTP server on localhost
2. Prints a URL for the user to open in their REAL browser
3. The page shows instructions + a bookmarklet to copy cookies
4. User logs in to Reddit in their real browser, clicks the bookmarklet
5. Cookies are sent back to the local server and saved

Zero anti-bot needed — the user uses their normal Chrome/Firefox/Edge.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .reddit_browser_login import _save_cookies_playwright_format, get_cookie_path

# ---------------------------------------------------------------------------
# HTML page served to the user
# ---------------------------------------------------------------------------

_HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ferrox Reddit Login</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#0f0f1a;color:#e0e0e0;line-height:1.6;padding:40px 20px;
       max-width:720px;margin:0 auto}
  h1{color:#FF4500;margin-bottom:8px}
  .subtitle{color:#a0a0b0;font-size:14px;margin-bottom:32px}
  .step{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:12px;
        padding:20px;margin-bottom:20px}
  .step-num{display:inline-block;background:#FF4500;color:#0f0f1a;
            font-weight:bold;width:28px;height:28px;border-radius:50%;
            text-align:center;line-height:28px;margin-right:10px}
  .step h3{display:inline;color:#fff;font-size:16px}
  .step p{margin-top:10px;color:#b0b0c0;font-size:14px}
  code{display:block;background:#0f0f1a;border:1px solid #3a3a5c;
       border-radius:8px;padding:12px;margin-top:10px;font-family:monospace;
       font-size:12px;color:#7bed9f;white-space:pre-wrap;word-break:break-all;
       cursor:pointer;user-select:all}
  code:hover{background:#151525}
  .btn{display:inline-block;background:#FF4500;color:#fff;border:none;
       padding:12px 24px;border-radius:8px;font-weight:bold;cursor:pointer;
       font-size:14px;margin-top:10px;text-decoration:none}
  .btn:hover{background:#ff6b35}
  .btn-secondary{background:#2a2a4e;color:#e0e0e0}
  .btn-secondary:hover{background:#3a3a5e}
  textarea{width:100%;min-height:200px;background:#0f0f1a;border:1px solid #3a3a5c;
           border-radius:8px;padding:12px;color:#e0e0e0;font-family:monospace;
           font-size:12px;margin-top:10px;resize:vertical}
  textarea:focus{outline:none;border-color:#FF4500}
  .status{margin-top:16px;padding:12px;border-radius:8px;font-size:14px}
  .status.ok{background:#1a3a2e;color:#7bed9f;border:1px solid #2a5a3e}
  .status.err{background:#3a1a1a;color:#ff6b6b;border:1px solid #5a2a2a}
  .hidden{display:none}
</style>
</head>
<body>
<h1>Ferrox Reddit Login</h1>
<p class="subtitle">Log in to Reddit using your real browser — no automation detected</p>

<div class="step">
  <span class="step-num">1</span>
  <h3>Open Reddit in your real browser</h3>
  <p>Click the button below to open <b>reddit.com</b> in a new tab. Log in normally with
     your username, password, and any 2FA.</p>
  <a class="btn" href="https://www.reddit.com/login/" target="_blank">Open reddit.com/login</a>
</div>

<div class="step">
  <span class="step-num">2</span>
  <h3>Copy the auto-cookie bookmarklet</h3>
  <p>After logging in, drag this button to your bookmarks bar, then click it while
     on any reddit.com page. It will copy all cookies to your clipboard.</p>
  <a class="btn btn-secondary" href="javascript:(function(){const d=document;const c=d.cookie.split(';').map(s=>{const[p,...v]=s.trim().split('=');return{name:p.trim(),value:v.join('='),domain:location.hostname,path:'/',secure:true,httpOnly:false};});const h=['reddit_session','token_v2','session_tracker','loid','csv2'];const f=c.filter(x=>h.some(hn=>x.name.toLowerCase().includes(hn.toLowerCase()))||x.name.startsWith('_')||x.name.length>10);const j=JSON.stringify(f.length?f:c,null,2);navigator.clipboard.writeText(j).then(()=>alert('Cookies copied! Paste them in the Ferrox page.')).catch(()=>prompt('Copy this JSON:',j));})();">Copy Reddit Cookies</a>
  <p style="margin-top:12px"><b>Or</b> open DevTools (F12) → Application → Cookies → https://reddit.com,<br>
     right-click → Copy all, and paste the JSON below.</p>
</div>

<div class="step">
  <span class="step-num">3</span>
  <h3>Paste cookies here</h3>
  <p>Paste the cookie JSON you copied from the bookmarklet or DevTools:</p>
  <textarea id="cookies" placeholder='[{"name":"reddit_session","value":"...","domain":".reddit.com"},...]'></textarea>
  <br>
  <button class="btn" onclick="submitCookies()">Save Cookies to Ferrox</button>
  <div id="status" class="status hidden"></div>
</div>

<script>
function submitCookies() {
  const raw = document.getElementById('cookies').value.trim();
  const status = document.getElementById('status');
  if (!raw) {
    status.className = 'status err';
    status.textContent = 'Please paste cookies first.';
    status.classList.remove('hidden');
    return;
  }

  let parsed = null;

  // Try 1: Direct JSON
  try {
    const j = JSON.parse(raw);
    if (Array.isArray(j)) { parsed = j; }
    else if (typeof j === 'object' && j !== null) {
      parsed = Object.entries(j).map(([k,v]) => ({
        name:k, value:typeof v==='string'?v:JSON.stringify(v), domain:'.reddit.com', path:'/'
      }));
    }
  } catch(e) {}

  // Try 2: Tab-separated text (Chrome DevTools "Copy all")
  if (!parsed) {
    const lines = raw.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
    if (lines.length > 0 && lines[0].includes('\t')) {
      const parts = lines[0].split('\t');
      const isDevtools = parts.length >= 8 && ((parts[2]||'').includes('.reddit.com') || (parts[2]||'').includes('reddit.com'));
      const isNetscape = parts.length >= 7 && ((parts[0]||'').includes('.reddit.com') || (parts[0]||'').includes('reddit.com'));

      if (isDevtools) {
        const dataLines = lines.filter(l => !l.toLowerCase().startsWith('name\t'));
        parsed = dataLines.map(line => {
          const p = line.split('\t');
          return {
            name:  (p[0] || '').trim(),
            value: (p[1] || '').trim(),
            domain:(p[2] || '.reddit.com').trim(),
            path:  (p[3] || '/').trim(),
            secure: (p[7]||'').toString().includes('\u2713') || (p[7]||'').toString().toLowerCase()==='true',
            httpOnly: (p[6]||'').toString().includes('\u2713') || (p[6]||'').toString().toLowerCase()==='true',
          };
        }).filter(c => c.name && c.value);
      } else if (isNetscape) {
        parsed = lines.map(line => {
          const p = line.split('\t');
          return {
            domain: (p[0] || '.reddit.com').trim(),
            path:   (p[2] || '/').trim(),
            secure: (p[3] || '').toLowerCase()==='true',
            name:   (p[5] || '').trim(),
            value:  (p[6] || '').trim(),
          };
        }).filter(c => c.name && c.value);
      }
    }
  }

  if (!parsed || parsed.length === 0) {
    status.className = 'status err';
    status.textContent = 'Could not parse cookies. Use Chrome DevTools: Application -> Cookies -> https://reddit.com -> right-click -> Copy all. Or use the bookmarklet.';
    status.classList.remove('hidden');
    return;
  }

  status.className = 'status ok';
  status.textContent = 'Parsed ' + parsed.length + ' cookies. Saving...';
  status.classList.remove('hidden');

  fetch('/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(parsed)
  })
  .then(r => r.text())
  .then(msg => {
    status.className = 'status ok';
    status.textContent = '[OK] ' + msg;
  })
  .catch(e => {
    status.className = 'status err';
    status.textContent = '[X] Error: ' + e.message;
  });
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _CookieHandler(BaseHTTPRequestHandler):
    """Handles GET / (serve HTML) and POST /save (receive cookies)."""

    # Shared state across requests
    saved: bool = False
    result_msg: str = ""
    cookie_path: Path = Path()

    def log_message(self, fmt: str, *args) -> None:
        # Suppress default logging noise
        pass

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            body = _HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/save":
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = self.rfile.read(length).decode("utf-8")
                cookies = json.loads(payload)

                if not isinstance(cookies, list):
                    self._send_json(400, {"error": "Expected JSON array of cookies"})
                    return

                # Save in Playwright format
                _save_cookies_playwright_format(cookies, self.cookie_path)

                _CookieHandler.saved = True
                _CookieHandler.result_msg = (
                    f"Saved {len(cookies)} cookies to Ferrox! "
                    f"You can close this tab and run '/reddit start'."
                )
                self._send_json(200, {"message": _CookieHandler.result_msg})
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

def _find_free_port(start: int = 8765, end: int = 8899) -> int:
    """Find an available TCP port in the given range."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
    raise RuntimeError("No free port found in range")


def _run_server(port: int, cookie_path: Path, shutdown_event: threading.Event) -> None:
    """Run the HTTP server in a background thread."""
    _CookieHandler.cookie_path = cookie_path
    _CookieHandler.saved = False
    _CookieHandler.result_msg = ""

    server = HTTPServer(("127.0.0.1", port), _CookieHandler)

    # Poll shutdown event so we can stop gracefully
    def serve() -> None:
        server.timeout = 1.0
        while not shutdown_event.is_set():
            server.handle_request()
        server.server_close()

    threading.Thread(target=serve, daemon=True).start()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def reddit_login_via_local_server(timeout_seconds: int = 300) -> str:
    """Start a local HTTP server, print a URL, and wait for cookie paste.

    The user opens the printed URL in their real browser, logs in to Reddit,
    copies cookies via the provided bookmarklet or DevTools, pastes them
    into the form, and the server saves them for PRAW / browser reuse.

    Args:
        timeout_seconds: Maximum seconds to wait for user submission.

    Returns:
        Human-readable success or error message.
    """
    cookie_path = get_cookie_path()
    cookie_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        port = _find_free_port()
    except RuntimeError as exc:
        return f"Could not find a free local port: {exc}"

    shutdown_event = threading.Event()
    _run_server(port, cookie_path, shutdown_event)

    url = f"http://localhost:{port}/"

    # Print instructions
    print("\n" + "=" * 62)
    print("  Reddit Login via Real Browser")
    print("=" * 62)
    print("  A local server is running. Open this URL in your REAL browser:")
    print()
    print(f"    {url}")
    print()
    print("  Follow the steps on the page:")
    print("    1. Open reddit.com/login and log in normally")
    print("    2. Use the bookmarklet or DevTools to copy cookies")
    print("    3. Paste into the form and click Save")
    print()
    print(f"  Waiting up to {timeout_seconds} seconds for you to submit...")
    print("=" * 62 + "\n")

    # Poll for save completion
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        if _CookieHandler.saved:
            shutdown_event.set()
            return f"{_CookieHandler.result_msg}"
        await asyncio.sleep(1.0)

    # Timeout
    shutdown_event.set()
    return (
        "Timed out waiting for cookies.\n"
        f"The server at {url} is no longer listening.\n"
        "Please try '/reddit login' again."
    )
