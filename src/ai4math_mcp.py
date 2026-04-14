"""AI4Math unified MCP server.

Consolidates everything previously split across 4 servers (lean_mcp,
lean_search_mcp, web_search_mcp, pdf_mcp) into one stdio process. This
simplifies the recipe to a single stdio extension and saves ~150 MB RSS
+ 1 second of startup time.

Tools (namespace in Goose: `ai4math__*`):

  Lean verification
    lean_check(code, import_line)       compile Lean 4 code via lean-checker
    lean_health()                        ping the lean-checker service

  Mathlib search (4 engines)
    lean_search_engines()                health-check of all 4 + comparison
    lean_search_loogle(query)            type/pattern search (Loogle)
    lean_search_leansearch(query, n)     semantic with informal descriptions
    lean_search_moogle(query)            neural, best-effort
    lean_search_scilib(lean_code, n)     SciLib GraphRAG premise retrieval

  Web
    web_search(query, n)                 Brave (if API key) or DuckDuckGo
    web_fetch(url, max_chars)            GET + HTML→text + truncate

  PDF
    pdf_info(path)                       metadata, pages, size
    pdf_read(path, pages, max_chars)     extract text from page range
    pdf_search(path, query, context)     substring search with context

Env (all optional):
  LEAN_CHECKER_URL  http://localhost:8888
  SCILIB_GRAG_URL   https://scilib.tailb97193.ts.net/grag
  LEANSEARCH_URL    https://leansearch.net
  LOOGLE_URL        https://loogle.lean-lang.org
  MOOGLE_URL        https://www.moogle.ai
  BRAVE_API_KEY     (optional, enables Brave Search API instead of DDG)

  AI4MATH_LEAN_DISABLED=1  — disable lean_check/lean_health
  AI4MATH_WEB_DISABLED=1   — disable web_search/web_fetch
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader

mcp = FastMCP("ai4math")

# ---------- config ----------

LEAN_CHECKER_URL = os.environ.get("LEAN_CHECKER_URL", "http://localhost:8888").rstrip("/")
SCILIB = os.environ.get("SCILIB_GRAG_URL", "https://scilib.tailb97193.ts.net/grag").rstrip("/")
LEANSEARCH = os.environ.get("LEANSEARCH_URL", "https://leansearch.net").rstrip("/")
LOOGLE = os.environ.get("LOOGLE_URL", "https://loogle.lean-lang.org").rstrip("/")
MOOGLE = os.environ.get("MOOGLE_URL", "https://www.moogle.ai").rstrip("/")

LEAN_DISABLED = os.environ.get("AI4MATH_LEAN_DISABLED") == "1"
WEB_DISABLED = os.environ.get("AI4MATH_WEB_DISABLED") == "1"

UA = "Mozilla/5.0 (X11; Linux x86_64) AI4Math/1.0"
MAX_RESULTS = 10
CHARS_PER_HIT = 400
PDF_DEFAULT_MAX_CHARS = 8000
WEB_DEFAULT_MAX_CHARS = 3000


def _fmt_err(tool: str, e: Exception) -> str:
    return f"ERROR [{tool}]: {type(e).__name__}: {str(e)[:300]}"


def _truncate(s: str | None, n: int = CHARS_PER_HIT) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


# ========================================================================
# Lean verification
# ========================================================================

def _lean_format_ok() -> str:
    return "OK: Lean 4 code compiles successfully (Mathlib imported)."


def _lean_format_errors(payload: dict) -> str:
    msgs = payload.get("messages") or []
    if not msgs:
        stderr = (payload.get("stderr") or "").strip()
        stdout = (payload.get("stdout") or "").strip()
        return f"ERROR (rc={payload.get('returncode')}):\nstdout:\n{stdout}\nstderr:\n{stderr}"
    lines = [f"ERROR: Lean reported {len(msgs)} diagnostic(s):"]
    for m in msgs:
        sev = m.get("severity") or "?"
        line = m.get("line")
        col = m.get("column")
        loc = f"L{line}:C{col}" if line is not None else "?"
        text = (m.get("message") or "").strip()
        lines.append(f"  [{sev} @ {loc}] {text}")
    return "\n".join(lines)


@mcp.tool()
def lean_check(code: str, import_line: str = "import Mathlib") -> str:
    """Type-check and compile Lean 4 code against Mathlib (v4.24).

    Pass a Lean 4 source snippet as `code`. Mathlib is automatically imported
    unless the code already contains an `import` statement. Returns either
    'OK: ...' on successful compilation, or a human-readable error report
    with line/column coordinates for each diagnostic.

    Example:
        lean_check("example : 1 + 1 = 2 := by norm_num")
    """
    if LEAN_DISABLED:
        return "ERROR: lean_check is disabled via AI4MATH_LEAN_DISABLED."
    try:
        resp = requests.post(
            f"{LEAN_CHECKER_URL}/check",
            json={"code": code, "import_line": import_line},
            timeout=120,
        )
    except requests.ConnectionError:
        return (
            f"ERROR: cannot reach lean-checker at {LEAN_CHECKER_URL}. "
            "Is the docker container running? "
            "Start it with: cd vendor/lean-checker && docker compose up -d"
        )
    except requests.Timeout:
        return "ERROR: lean-checker timed out after 120 s."
    if resp.status_code != 200:
        return f"ERROR: lean-checker HTTP {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    return _lean_format_ok() if data.get("ok") else _lean_format_errors(data)


@mcp.tool()
def lean_health() -> str:
    """Check that the lean-checker service is up and Lean/Mathlib are working."""
    if LEAN_DISABLED:
        return "lean-checker: disabled via AI4MATH_LEAN_DISABLED"
    try:
        resp = requests.get(f"{LEAN_CHECKER_URL}/health", timeout=10)
        resp.raise_for_status()
        return f"lean-checker: {resp.json()}"
    except Exception as e:
        return f"ERROR: lean-checker health check failed: {type(e).__name__}: {e}"


# ========================================================================
# Mathlib search (4 engines)
# ========================================================================

@mcp.tool()
def lean_search_engines() -> str:
    """List available Lean/Mathlib search engines and their current health status.

    Use this BEFORE doing any Lean search to let the user pick which engine
    when the user has not already named one. Each engine has different strengths:
      - loogle     : type/pattern search ("`?a + ?b = ?b + ?a`")
      - leansearch : semantic with informal English ("commutativity of addition")
      - moogle     : neural similarity (best-effort; sometimes down)
      - scilib     : GraphRAG premise retrieval (Lean 4 goal with `sorry` → hints)
    """
    lines = ["Доступные Mathlib search движки:\n"]
    engines = [
        ("loogle", f"{LOOGLE}/json?q=ping"),
        ("leansearch", f"{LEANSEARCH}/openapi.json"),
        ("moogle", f"{MOOGLE}/"),
        ("scilib", f"{SCILIB}/health"),
    ]
    for name, probe in engines:
        try:
            r = requests.get(probe, timeout=4)
            status = "OK" if r.status_code < 500 else f"HTTP {r.status_code}"
        except Exception as e:
            status = f"DOWN ({type(e).__name__})"
        lines.append(f"  - {name:12s}  {status}")
    lines.append("")
    lines.append(
        "Если пользователь уже назвал конкретный движок в промпте — "
        "вызывай его напрямую. Если нет — спроси, какой использовать."
    )
    return "\n".join(lines)


@mcp.tool()
def lean_search_loogle(query: str) -> str:
    """Search Mathlib via Loogle — type/pattern search.

    Good for: "I need a lemma whose type matches `? + ? = ? + ?`".
    Query syntax: standard Loogle, e.g. `Nat.add_comm`, `?a + ?b = ?b + ?a`,
    `|- _ < _`, or free text like `commutativity addition`.
    """
    try:
        r = requests.get(f"{LOOGLE}/json", params={"q": query}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return _fmt_err("loogle", e)
    hits = (data.get("hits") or [])[:MAX_RESULTS]
    header = data.get("header", f"Loogle: {data.get('count', 0)} results")
    lines = [f"Loogle — {header.strip()}"]
    for h in hits:
        lines.append(
            f"  • {h.get('name')}  ::  {_truncate(h.get('type'), 200)}\n"
            f"    module: {h.get('module')}"
        )
        if h.get("doc"):
            lines.append(f"    doc: {_truncate(h['doc'], 200)}")
    return "\n".join(lines) if hits else f"{header}\n(нет результатов)"


@mcp.tool()
def lean_search_leansearch(query: str, num_results: int = 5) -> str:
    """Search Mathlib via LeanSearch — semantic with informal English descriptions.

    Good for: natural-language queries like "commutativity of multiplication on
    the integers" or "Cauchy criterion for convergent series".
    """
    try:
        r = requests.post(
            f"{LEANSEARCH}/search",
            json={"query": [query], "num_results": min(num_results, MAX_RESULTS)},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return _fmt_err("leansearch", e)
    items = data[0] if isinstance(data, list) and data else []
    if not items:
        return f"LeanSearch: пусто по запросу «{query}»"
    lines = [f"LeanSearch — {len(items)} результатов по «{query}»"]
    for it in items:
        res = it.get("result") or {}
        name = ".".join(res.get("name") or [])
        module = ".".join(res.get("module_name") or [])
        lines.append(
            f"  • {name}  (dist={it.get('distance', 0):.3f})"
            f"\n    type: {_truncate(res.get('type') or res.get('signature'), 200)}"
            f"\n    module: {module}"
        )
        if res.get("informal_description"):
            lines.append(f"    informal: {_truncate(res['informal_description'], 300)}")
    return "\n".join(lines)


@mcp.tool()
def lean_search_moogle(query: str) -> str:
    """Search Mathlib via Moogle — neural semantic search (best-effort; may be down)."""
    try:
        r = requests.post(
            f"{MOOGLE}/api/search",
            json=[{"isFind": False, "contents": query}],
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return _fmt_err("moogle", e)
    return f"Moogle — raw response:\n{_truncate(json.dumps(data, ensure_ascii=False), 1500)}"


@mcp.tool()
def lean_search_scilib(lean_code: str, num_results: int = 10) -> str:
    """SciLib GraphRAG premise retrieval for Lean 4.

    Input: a Lean 4 theorem statement, optionally with `sorry` placeholder.
    Output: categorized hints (apply / rw / simp) derived via GraphDB ontology
    expansion + Qdrant vector search. Zero LLM calls. Best used when you
    already have a Lean goal and want concrete lemmas to try.
    """
    try:
        r = requests.post(
            f"{SCILIB}/search",
            json={
                "lean_code": lean_code,
                "num_results": min(num_results, 50),
                "include_vector": True,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return _fmt_err("scilib", e)
    pieces = []
    if data.get("hints_text"):
        pieces.append(
            f"SciLib GraphRAG hints (processing {data.get('processing_time_ms', '?')} ms):\n"
        )
        pieces.append(_truncate(data["hints_text"], 2000))
    hints = data.get("hints_list") or []
    if hints:
        pieces.append(f"\n\nStructured ({len(hints)} items):")
        for h in hints[:num_results]:
            pieces.append(
                f"  • [{h.get('role')}] {h.get('name')}  ::  {_truncate(h.get('signature'), 200)}"
            )
    return "\n".join(pieces) if pieces else f"SciLib: пусто. features={data.get('features')}"


# ========================================================================
# Web search / fetch
# ========================================================================

def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style|noscript)[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _ddg_search(query: str, num: int) -> list[dict]:
    r = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": UA},
        timeout=20,
    )
    r.raise_for_status()
    html = r.text
    results = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        flags=re.DOTALL,
    ):
        url, title, snippet = m.group(1), _strip_html(m.group(2)), _strip_html(m.group(3))
        if url.startswith("//duckduckgo.com/l/?uddg="):
            q = parse_qs(urlparse("https:" + url).query)
            url = q.get("uddg", [url])[0]
        results.append({"url": url, "title": title, "snippet": snippet[:400]})
        if len(results) >= num:
            break
    return results


def _brave_search(query: str, num: int, api_key: str) -> list[dict]:
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": num},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    out = []
    for w in (data.get("web") or {}).get("results", [])[:num]:
        out.append(
            {
                "url": w.get("url"),
                "title": w.get("title"),
                "snippet": w.get("description", "")[:400],
            }
        )
    return out


@mcp.tool()
def web_search(query: str, num_results: int = 5) -> str:
    """Search the open web. Returns title/url/snippet for each result.

    Uses Brave Search API if `BRAVE_API_KEY` env var is set, otherwise falls
    back to DuckDuckGo HTML scraping (keyless, best-effort).
    """
    if WEB_DISABLED:
        return "ERROR: web_search is disabled via AI4MATH_WEB_DISABLED."
    key = os.environ.get("BRAVE_API_KEY")
    n = min(max(num_results, 1), MAX_RESULTS)
    try:
        results = _brave_search(query, n, key) if key else _ddg_search(query, n)
    except Exception as e:
        return _fmt_err("web_search", e)
    if not results:
        return f"Ничего не найдено по запросу «{query}»."
    lines = [f"Результаты по «{query}» (провайдер: {'brave' if key else 'duckduckgo'}):"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    return "\n".join(lines)


@mcp.tool()
def web_fetch(url: str, max_chars: int = WEB_DEFAULT_MAX_CHARS) -> str:
    """Fetch a URL and return its text content.

    HTML is stripped of tags. Content is truncated to `max_chars` chars
    (default 3000). Call multiple times with different URLs for separate fetches.
    """
    if WEB_DISABLED:
        return "ERROR: web_fetch is disabled via AI4MATH_WEB_DISABLED."
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
    except Exception as e:
        return _fmt_err("web_fetch", e)
    ct = r.headers.get("Content-Type", "")
    body = r.text
    if "html" in ct.lower():
        body = _strip_html(body)
    if len(body) > max_chars:
        body = body[:max_chars] + f"\n\n[... truncated, total {len(r.text)} chars ...]"
    return f"{url}\nContent-Type: {ct}\n\n{body}"


# ========================================================================
# PDF
# ========================================================================

def _pdf_resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _pdf_parse_pages(spec: str, total: int) -> list[int]:
    pages: set[int] = set()
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            for i in range(start, end + 1):
                if 1 <= i <= total:
                    pages.add(i - 1)
        else:
            i = int(part)
            if 1 <= i <= total:
                pages.add(i - 1)
    return sorted(pages)


@mcp.tool()
def pdf_info(path: str) -> str:
    """Return page count, metadata, and file size for a local PDF."""
    p = _pdf_resolve(path)
    if not p.exists():
        return f"ERROR: файл не найден: {p}"
    try:
        reader = PdfReader(str(p))
    except Exception as e:
        return _fmt_err("pdf_info", e)
    n = len(reader.pages)
    meta = reader.metadata or {}
    size = p.stat().st_size
    lines = [f"PDF: {p}", f"Страниц: {n}", f"Размер: {size} байт"]
    for k in ("/Title", "/Author", "/Subject", "/Creator", "/Producer"):
        if meta.get(k):
            lines.append(f"{k[1:]}: {meta[k]}")
    return "\n".join(lines)


@mcp.tool()
def pdf_read(path: str, pages: str = "1-5", max_chars: int = PDF_DEFAULT_MAX_CHARS) -> str:
    """Extract text from specified pages of a local PDF.

    `pages` is a 1-indexed spec, e.g. "1-3", "1,3,5", "1-5,10". Default first 5.
    Text is truncated to `max_chars` characters (default 8000).
    """
    p = _pdf_resolve(path)
    if not p.exists():
        return f"ERROR: файл не найден: {p}"
    try:
        reader = PdfReader(str(p))
    except Exception as e:
        return _fmt_err("pdf_read", e)
    total = len(reader.pages)
    idxs = _pdf_parse_pages(pages, total)
    if not idxs:
        return f"ERROR: пустой или некорректный диапазон «{pages}» (всего {total})"
    parts = []
    for i in idxs:
        try:
            txt = reader.pages[i].extract_text() or ""
        except Exception as e:
            txt = f"[error on page {i + 1}: {e}]"
        parts.append(f"\n=== стр. {i + 1} ===\n{txt.strip()}")
    out = "\n".join(parts).strip()
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n\n[... truncated, {len(out) - max_chars} chars cut ...]"
    return out


@mcp.tool()
def pdf_search(path: str, query: str, context: int = 120) -> str:
    """Case-insensitive substring search over a PDF, returning matches with
    page number and surrounding context (±`context` chars)."""
    p = _pdf_resolve(path)
    if not p.exists():
        return f"ERROR: файл не найден: {p}"
    try:
        reader = PdfReader(str(p))
    except Exception as e:
        return _fmt_err("pdf_search", e)
    q = query.lower()
    hits: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            continue
        lower = txt.lower()
        start = 0
        while True:
            j = lower.find(q, start)
            if j == -1:
                break
            a, b = max(0, j - context), min(len(txt), j + len(query) + context)
            snippet = txt[a:b].replace("\n", " ")
            hits.append(f"стр. {i + 1}: ...{snippet}...")
            start = j + len(query)
            if len(hits) >= 30:
                break
        if len(hits) >= 30:
            break
    if not hits:
        return f"«{query}» не найдено в {p}"
    return f"{len(hits)} совпадений:\n" + "\n".join(hits)


if __name__ == "__main__":
    mcp.run()
