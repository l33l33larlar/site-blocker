"""Minimal Chrome DevTools client over --remote-debugging-pipe (no third-party packages)."""
import base64
import fcntl
import json
import os
import select
import subprocess
import time

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class Chrome:
    def __init__(self, profile_dir, extra_args=()):
        to_r, to_w = os.pipe()
        from_r, from_w = os.pipe()

        def setup():
            r = fcntl.fcntl(to_r, fcntl.F_DUPFD, 20)
            w = fcntl.fcntl(from_w, fcntl.F_DUPFD, 20)
            os.dup2(r, 3)
            os.dup2(w, 4)

        args = [
            CHROME,
            "--headless=new",
            "--user-data-dir=" + profile_dir,
            "--remote-debugging-pipe",
            "--enable-unsafe-extension-debugging",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1100,900",
            *extra_args,
            "about:blank",
        ]
        self.proc = subprocess.Popen(
            args, preexec_fn=setup, pass_fds=(3, 4),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        os.close(to_r)
        os.close(from_w)
        self.w = to_w
        self.r = from_r
        self.buf = b""
        self.next_id = 0
        self.events = []

    def _read_message(self, timeout):
        deadline = time.time() + timeout
        while b"\0" not in self.buf:
            left = deadline - time.time()
            if left <= 0:
                return None
            ready, _, _ = select.select([self.r], [], [], left)
            if not ready:
                return None
            data = os.read(self.r, 1 << 20)
            if not data:
                raise RuntimeError("Chrome closed the pipe: " + self.stderr_tail())
            self.buf += data
        raw, self.buf = self.buf.split(b"\0", 1)
        return json.loads(raw)

    def stderr_tail(self):
        try:
            self.proc.wait(timeout=2)
            return self.proc.stderr.read().decode("utf-8", "replace")[-2000:]
        except Exception:
            return "(still running)"

    def send(self, method, params=None, session=None, timeout=30):
        self.next_id += 1
        msg = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        os.write(self.w, json.dumps(msg).encode() + b"\0")
        deadline = time.time() + timeout
        while True:
            m = self._read_message(max(0.01, deadline - time.time()))
            if m is None:
                raise TimeoutError(method)
            if m.get("id") == self.next_id:
                if "error" in m:
                    raise RuntimeError("%s -> %s" % (method, m["error"]))
                return m.get("result", {})
            self.events.append(m)

    def pump(self, seconds):
        """Keep reading events for a while."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            m = self._read_message(deadline - time.time())
            if m is not None:
                self.events.append(m)

    def targets(self):
        return self.send("Target.getTargets")["targetInfos"]

    def attach(self, target_id):
        return self.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})["sessionId"]

    def evaluate(self, session, expression, timeout=30):
        res = self.send(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
            session=session, timeout=timeout,
        )
        if "exceptionDetails" in res:
            raise RuntimeError("JS error: " + json.dumps(res["exceptionDetails"])[:800])
        return res["result"].get("value")

    def open(self, url, wait=2.5):
        tid = self.send("Target.createTarget", {"url": url})["targetId"]
        self.pump(wait)
        return tid

    def url_of(self, target_id):
        for t in self.targets():
            if t["targetId"] == target_id:
                return t["url"]
        return None

    def screenshot(self, session, path):
        data = self.send("Page.captureScreenshot", {"format": "png"}, session=session)["data"]
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))

    def close(self):
        try:
            self.send("Browser.close", timeout=5)
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
