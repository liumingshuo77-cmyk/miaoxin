# -*- coding: utf-8 -*-
"""秒薪本地服务：页面、记账，以及股票行情代理。

行情来自腾讯证券；美股、港股若腾讯日线不完整，月初价改向雅虎财经取。
只绑定本机，供自己记账，不能当作交易报价。
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

def _dirs():
    here = Path(__file__).resolve().parent
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent, Path(getattr(sys, "_MEIPASS", here))
    return here, here


DATA_ROOT, FILE_ROOT = _dirs()
ROOT = FILE_ROOT
STATE_PATH = DATA_ROOT / "state.json"
UA = "Mozilla/5.0"
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class Cache:
    def __init__(self):
        self.lock = threading.Lock()
        self.mem = {}

    def get(self, key):
        with self.lock:
            item = self.mem.get(key)
            if not item:
                return None, False
            ts, ttl, val = item
            if time.time() - ts > ttl:
                return None, False
            return val, True

    def put(self, key, val, ttl):
        with self.lock:
            self.mem[key] = (time.time(), ttl, val)


cache = Cache()


def get_bytes(url, referer, timeout=8):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Referer": referer, "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fnum(value):
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def valid_symbol(symbol):
    return re.fullmatch(r"(sh|sz|bj)\d{6}|hk\d{5}|us[A-Z][A-Z0-9\-]{0,9}", symbol or "") is not None


def to_symbol(market, code):
    market = (market or "").lower()
    code = (code or "").strip()
    symbol = None
    if market == "us":
        base = code.split(".")[0].upper()
        if re.fullmatch(r"[A-Z][A-Z0-9\-]{0,9}", base or ""):
            symbol = "us" + base
    elif market == "hk":
        digits = re.sub(r"\D", "", code)
        if digits:
            symbol = "hk" + digits.zfill(5)[-5:]
    elif market in ("sh", "sz", "bj") and re.fullmatch(r"\d{6}", code):
        symbol = market + code
    if not valid_symbol(symbol):
        return None
    return symbol


def normalize_user(raw):
    text = re.sub(r"\s+", "", raw or "")
    if not text:
        return None
    low = text.lower()
    matched = re.fullmatch(r"(sh|sz|bj|hk|us)([0-9a-z.\-]+)", low)
    if matched:
        code = matched.group(2).upper() if matched.group(1) == "us" else matched.group(2)
        return to_symbol(matched.group(1), code)
    if re.fullmatch(r"\d{1,5}", text):
        return to_symbol("hk", text)
    if re.fullmatch(r"\d{6}", text):
        if text.startswith("920") or text[0] in "48":
            return to_symbol("bj", text)
        if text[0] in "569":
            return to_symbol("sh", text)
        return to_symbol("sz", text)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,9}", text):
        return to_symbol("us", text)
    return None


def nice_time(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) >= 14:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]} {digits[8:10]}:{digits[10:12]}:{digits[12:14]}"
    return raw or ""


def extract_time(fields):
    for field in fields:
        if re.fullmatch(r"\d{14}", field) or re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}", field):
            return nice_time(field)
    return ""


def currency_of(fields, symbol):
    for field in fields:
        if field in ("CNY", "HKD", "USD"):
            return field
    if symbol.startswith("hk"):
        return "HKD"
    if symbol.startswith("us"):
        return "USD"
    return "CNY"


def decode_qt(raw):
    try:
        return raw.decode("gbk")
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace")


def parse_qt(text):
    found = {}
    for matched in re.finditer(r'v_([A-Za-z0-9\.]+)="([^"]*)"', text):
        symbol = normalize_user(matched.group(1))
        fields = matched.group(2).split("~")
        if not symbol or len(fields) < 5:
            continue
        price = fnum(fields[3])
        prev = fnum(fields[4])
        if price is None:
            continue
        found[symbol] = {
            "symbol": symbol,
            "name": fields[1],
            "code": fields[2],
            "price": price,
            "prevClose": prev,
            "time": extract_time(fields),
            "currency": currency_of(fields, symbol),
        }
    return found


def fetch_quote_map(symbols):
    symbols = [s for s in symbols if valid_symbol(s)]
    out = {}
    need = []
    for symbol in symbols:
        hit, ok = cache.get("q:" + symbol)
        if ok:
            out[symbol] = hit
        else:
            need.append(symbol)
    if not need:
        return out
    raw = get_bytes("https://qt.gtimg.cn/q=" + ",".join(need), "https://gu.qq.com/", timeout=8)
    parsed = parse_qt(decode_qt(raw))
    for symbol in need:
        item = parsed.get(symbol)
        if item:
            cache.put("q:" + symbol, item, 3)
            out[symbol] = item
    return out


def fetch_fx():
    hit, ok = cache.get("fx")
    if ok:
        return hit
    fx = {"CNY": 1.0}
    try:
        raw = get_bytes("https://qt.gtimg.cn/q=whUSDCNY,whHKDCNY", "https://gu.qq.com/", timeout=8)
        text = decode_qt(raw)
        for matched in re.finditer(r'v_([A-Za-z0-9]+)="([^"]*)"', text):
            fields = matched.group(2).split("~")
            price = fnum(fields[3]) if len(fields) > 3 else None
            if price is None:
                continue
            key = matched.group(1).upper()
            if "USD" in key:
                fx["USD"] = price
            elif "HKD" in key:
                fx["HKD"] = price
    except Exception:
        pass
    cache.put("fx", fx, 60)
    return fx


def parse_bars(rows):
    bars = []
    for row in rows or []:
        if len(row) < 3:
            continue
        close = fnum(row[2])
        if close is None or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row[0])):
            continue
        bars.append((row[0], close))
    return bars


def tencent_bars(symbol):
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,90,"
    raw = get_bytes(url, "https://gu.qq.com/", timeout=8)
    payload = json.loads(raw.decode("utf-8"))
    data = payload.get("data") or {}
    node = data.get(symbol)
    if node is None and len(data) == 1:
        node = next(iter(data.values()))
    node = node or {}
    return parse_bars(node.get("day") or node.get("qfqday") or [])


def yahoo_symbol(symbol):
    if symbol.startswith("us"):
        return symbol[2:].replace(".", "-")
    if symbol.startswith("hk"):
        code = symbol[2:].lstrip("0") or "0"
        return code.zfill(4) + ".HK"
    if symbol.startswith("sh"):
        return symbol[2:] + ".SS"
    if symbol.startswith("sz"):
        return symbol[2:] + ".SZ"
    return None


def yahoo_bars(symbol):
    ys = yahoo_symbol(symbol)
    if not ys:
        return []
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(ys)
        + "?interval=1d&range=3mo"
    )
    raw = get_bytes(url, "https://finance.yahoo.com/", timeout=8)
    payload = json.loads(raw.decode("utf-8"))
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return []
    result = result[0]
    tz = ZoneInfo(result.get("meta", {}).get("exchangeTimezoneName") or "America/New_York")
    stamps = result.get("timestamp") or []
    closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    bars = []
    for ts, close in zip(stamps, closes):
        number = fnum(close)
        if number is None:
            continue
        day = datetime.fromtimestamp(ts, tz).date().isoformat()
        bars.append((day, number))
    return bars


def pick_ref(bars, month_start):
    start = datetime.strptime(month_start, "%Y-%m-%d").date()
    best_day = None
    best_close = None
    for day, close in bars:
        try:
            current = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            continue
        if current < start and (best_day is None or current > best_day):
            best_day = current
            best_close = close
    if best_day is None or (start - best_day).days > 15:
        return None
    return best_close


def month_ref(symbol, month):
    key = f"m:{symbol}:{month}"
    hit, ok = cache.get(key)
    if ok:
        return hit
    ref = None
    try:
        ref = pick_ref(tencent_bars(symbol), month + "-01")
    except Exception:
        ref = None
    if ref is None:
        try:
            ref = pick_ref(yahoo_bars(symbol), month + "-01")
        except Exception:
            ref = None
    cache.put(key, ref, 6 * 3600 if ref is not None else 120)
    return ref


def search_hints(query):
    query = (query or "").strip()
    if not query:
        return []
    url = "https://smartbox.gtimg.cn/s3/?v=2&q=" + urllib.parse.quote(query) + "&t=all"
    try:
        text = get_bytes(url, "https://gu.qq.com/", timeout=6).decode("utf-8", "replace")
    except Exception:
        return []
    matched = re.search(r'v_hint="(.*)"', text, re.S)
    if not matched:
        return []
    body = matched.group(1)
    if body in ("", "N"):
        return []
    out = []
    seen = set()
    for row in body.split("^"):
        parts = row.split("~")
        if len(parts) < 5 or not parts[4].startswith("GP"):
            continue
        symbol = to_symbol(parts[0], parts[1])
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append({
            "symbol": symbol,
            "name": parts[2],
            "code": parts[1],
            "market": parts[0].lower(),
            "type": parts[4],
        })
        if len(out) >= 8:
            break
    return out


def resolve(query):
    symbol = normalize_user(query)
    if symbol:
        try:
            got = fetch_quote_map([symbol])
        except Exception:
            got = {}
        item = got.get(symbol)
        if item and item.get("name"):
            return [{
                "symbol": symbol,
                "name": item["name"],
                "code": item.get("code") or symbol,
                "market": symbol[:2],
            }]
    return search_hints(query)


def quote_payload(qs):
    month = (qs.get("month") or [datetime.now().strftime("%Y-%m")])[0]
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        month = datetime.now().strftime("%Y-%m")
    raw = (qs.get("symbols") or [""])[0]
    symbols = []
    missing = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        symbol = normalize_user(part)
        if not symbol:
            missing.append(part)
        elif symbol not in symbols:
            symbols.append(symbol)
    symbols = symbols[:30]
    if not symbols:
        return {"fx": {"CNY": 1.0}, "quotes": [], "missing": missing}
    try:
        got = fetch_quote_map(symbols)
    except Exception:
        return {
            "fx": {"CNY": 1.0},
            "quotes": [],
            "missing": symbols + missing,
            "error": "行情源暂时连不上",
        }
    fx = fetch_fx()
    refs = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(month_ref, symbol, month): symbol for symbol in symbols}
        try:
            for fut in as_completed(futures, timeout=20):
                symbol = futures[fut]
                try:
                    refs[symbol] = fut.result()
                except Exception:
                    refs[symbol] = None
        except TimeoutError:
            pass
    quotes = []
    for symbol in symbols:
        base = got.get(symbol)
        if not base:
            missing.append(symbol)
            continue
        item = dict(base)
        item["fx"] = fx.get(item["currency"])
        item["monthRef"] = refs.get(symbol)
        quotes.append(item)
    return {"fx": fx, "quotes": quotes, "missing": missing}


def read_state():
    if not STATE_PATH.exists():
        return None
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_state(state):
    text = json.dumps(state, ensure_ascii=False, indent=2)
    if len(text.encode("utf-8")) > 1_000_000:
        raise ValueError("账本太大")
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(STATE_PATH)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        msg = fmt % args
        if "/api/quotes" in msg and " 200 " in " " + msg:
            return
        sys.stderr.write(msg + "\n")

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, name, content_type):
        path = ROOT / name
        if not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path == "/api/health":
                self.send_json({"ok": True, "app": "miaoxin"})
                return
            if parsed.path == "/api/state":
                self.send_json({"state": read_state()})
                return
            if parsed.path == "/api/quotes":
                self.send_json(quote_payload(qs))
                return
            if parsed.path == "/api/search":
                self.send_json({"matches": resolve((qs.get("q") or [""])[0])})
                return
            if parsed.path in FILES:
                self.send_file(*FILES[parsed.path])
                return
            self.send_error(404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/state":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > 1_000_000:
            self.send_json({"error": "too big"}, 413)
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
            state = data.get("state")
            if not isinstance(state, dict):
                raise ValueError("bad state")
            write_state(state)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        self.send_json({"ok": True})


class Server(ThreadingHTTPServer):
    allow_reuse_address = True


def health(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("app") == "miaoxin"
    except Exception:
        return False


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    open_browser = "--no-open" not in sys.argv
    for port in range(8765, 8775):
        if health(port):
            url = f"http://127.0.0.1:{port}/"
            print(f"秒薪已经在运行：{url}", flush=True)
            if open_browser:
                webbrowser.open(url)
            return
    httpd = None
    port = 8765
    for port in range(8765, 8775):
        try:
            httpd = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            httpd = None
    if httpd is None:
        raise SystemExit("端口 8765 到 8774 都被占了，关掉占用的程序再试。")
    url = f"http://127.0.0.1:{port}/"
    print(f"秒薪已启动 {url}", flush=True)
    print("关掉这个窗口就会停止。", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        httpd.shutdown()


if __name__ == "__main__":
    main()
