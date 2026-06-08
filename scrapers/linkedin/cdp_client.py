"""CDP Client for Chrome remote debugging protocol over WebSockets.

Provides clean methods to interact with a running Chrome instance to navigate,
scroll, and execute JavaScript.
"""

import json
import logging
import time
import requests
import websocket
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class CDPClient:
    """CDP Client to communicate with Chrome remote debugger."""
    
    def __init__(self, port: Optional[int] = None, host: Optional[str] = None):
        import os
        self.port = port if port is not None else int(os.getenv("CHROME_PORT", "9222"))
        self.host = host if host is not None else os.getenv("CHROME_HOST", "127.0.0.1")
        self.ws_url: Optional[str] = None
        self.ws: Optional[websocket.WebSocket] = None
        self.call_id = 0
        self.target_id: Optional[str] = None
        self.response_buffer: Dict[int, Dict[str, Any]] = {}
        self.event_buffer: List[Dict[str, Any]] = []

    def connect(self) -> None:
        """Connect to the browser, create a new target tab, and attach to it."""
        try:
            version_url = f"http://{self.host}:{self.port}/json/version"
            logger.info("Fetching browser info from %s", version_url)
            headers = {"Host": "localhost"}
            resp = requests.get(version_url, headers=headers, timeout=10)
            resp.raise_for_status()
            browser_info = resp.json()
            browser_ws_url = browser_info.get("webSocketDebuggerUrl")
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch Chrome remote debugger version info. Ensure Chrome is running with --remote-debugging-port={self.port}: {exc}") from exc

        if not browser_ws_url:
            raise RuntimeError("No browser debugger websocket URL found in /json/version")

        # Reconstruct browser_ws_url to use correct host:port
        from urllib.parse import urlparse, urlunparse
        try:
            parsed = urlparse(browser_ws_url)
            netloc = f"{self.host}:{self.port}"
            browser_ws_url = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        except Exception as e:
            logger.warning("Could not rewrite browser WebSocket URL host: %s", e)

        logger.info("Connecting to browser debugger at %s to create target", browser_ws_url)
        try:
            browser_ws = websocket.create_connection(browser_ws_url, timeout=20, header=["Host: localhost"])
            self.call_id += 1
            create_payload = {
                "id": self.call_id,
                "method": "Target.createTarget",
                "params": {"url": "about:blank"}
            }
            browser_ws.send(json.dumps(create_payload))
            resp_raw = browser_ws.recv()
            resp_data = json.loads(resp_raw)
            browser_ws.close()
        except Exception as exc:
            raise RuntimeError(f"Failed to communicate with browser debugger to create target tab: {exc}") from exc

        if "error" in resp_data:
            raise RuntimeError(f"Failed to create new target page: {resp_data['error']}")

        self.target_id = resp_data.get("result", {}).get("targetId")
        if not self.target_id:
            raise RuntimeError("Failed to obtain targetId from Target.createTarget response")

        self.ws_url = f"ws://{self.host}:{self.port}/devtools/page/{self.target_id}"
        logger.info("Connecting to newly created target page ID %s at %s", self.target_id, self.ws_url)
        self.ws = websocket.create_connection(self.ws_url, timeout=20, header=["Host: localhost"])
        self.ws.settimeout(20)
        self.call_id = 0
        self.response_buffer = {}
        self.event_buffer = []

    def call(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30) -> Dict[str, Any]:
        """Send a CDP request and wait for the response."""
        if not self.ws:
            raise RuntimeError("CDPClient is not connected. Call connect() first.")
        
        self.call_id += 1
        payload = {
            "id": self.call_id,
            "method": method,
            "params": params or {}
        }
        
        self.ws.settimeout(timeout)
        logger.debug("CDP Call %s: %s", self.call_id, method)
        self.ws.send(json.dumps(payload))
        
        # Check if response is already in buffer
        if self.call_id in self.response_buffer:
            res = self.response_buffer.pop(self.call_id)
            if "error" in res:
                raise RuntimeError(f"CDP error in {method}: {res['error']}")
            return res.get("result", {})
            
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"CDP call {method} timed out after {timeout} seconds")
            
            raw_msg = self.ws.recv()
            msg = json.loads(raw_msg)
            
            msg_id = msg.get("id")
            if msg_id is not None:
                if msg_id == self.call_id:
                    if "error" in msg:
                        raise RuntimeError(f"CDP error in {method}: {msg['error']}")
                    return msg.get("result", {})
                else:
                    self.response_buffer[msg_id] = msg
            else:
                # Buffer as asynchronous event
                self.event_buffer.append(msg)

    def eval_js(self, expression: str, timeout: float = 30, await_promise: bool = False) -> Any:
        """Evaluate a Javascript expression in the page context."""
        params = {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise
        }
        result = self.call("Runtime.evaluate", params, timeout=timeout)
        eval_result = result.get("result", {})
        
        if "exceptionDetails" in result:
            exception = result.get("exceptionDetails", {})
            text = exception.get("exception", {}).get("description", "Unknown JS error")
            logger.warning("JS execution exception: %s", text)
            return None
            
        return eval_result.get("value")

    def navigate(self, url: str, wait_seconds: float = 4) -> None:
        """Navigate the browser page to a new URL."""
        logger.info("Navigating target to %s", url)
        self.call("Page.navigate", {"url": url}, timeout=15)
        time.sleep(wait_seconds)

    def close(self) -> None:
        """Safely close the client connection and destroy the target tab."""
        if self.ws:
            try:
                self.ws.close()
            except Exception as exc:
                logger.debug("Failed closing websocket: %s", exc)
            finally:
                self.ws = None
                logger.info("CDPClient connection closed")
                
        if getattr(self, "target_id", None):
            try:
                version_url = f"http://{self.host}:{self.port}/json/version"
                headers = {"Host": "localhost"}
                browser_info = requests.get(version_url, headers=headers, timeout=10).json()
                browser_ws_url = browser_info.get("webSocketDebuggerUrl")
                if browser_ws_url:
                    # Reconstruct browser_ws_url to use correct host:port
                    from urllib.parse import urlparse, urlunparse
                    try:
                        parsed = urlparse(browser_ws_url)
                        netloc = f"{self.host}:{self.port}"
                        browser_ws_url = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
                    except Exception as e:
                        logger.warning("Could not rewrite browser WebSocket URL host in close(): %s", e)

                    browser_ws = websocket.create_connection(browser_ws_url, timeout=10, header=["Host: localhost"])
                    self.call_id += 1
                    close_payload = {
                        "id": self.call_id,
                        "method": "Target.closeTarget",
                        "params": {"targetId": self.target_id}
                    }
                    browser_ws.send(json.dumps(close_payload))
                    browser_ws.recv()
                    browser_ws.close()
                    logger.info("Closed target page ID %s", self.target_id)
            except Exception as exc:
                logger.warning("Failed to close target page %s: %s", self.target_id, exc)
            finally:
                self.target_id = None
