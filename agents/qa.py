"""QA agent: deterministic checks on a built product, plus an optional model review.

Step 3.2 runs every acceptance check defined in 3.1 and a fixed set of generic
checks against the files the builder produced. All of them are plain Python
(no model): the gate decision rests on them. The model review only adds bug
reports; a reported bug counts as an open critical/high bug only when its
severity is critical or high AND it gives a concrete reproduction. Those bugs
are labelled MODEL_REVIEW and never override a deterministic result.

Acceptance check shape (from 3.1):
    {"id": "AC1", "feature": "F1", "description": "...", "critical": true,
     "check": {"type": "file_exists" | "contains" | "regex" | "html_element" | "no_external_requests",
               "file": "product/index.html", "value": "..."}}

* contains      case-insensitive substring of the file
* regex         Python regular expression, searched with IGNORECASE and MULTILINE
* html_element  a simple selector: tag, #id, .class, [attr] or [attr=value] (one compound, e.g. button#export)
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

import guardrails
from agents.base import StepContext, call_agent
from llm import LLMError

ROLE = "qa"
INDEX = "product/index.html"
README = "product/README.md"
REQUIRED_FILES = (INDEX, README)
SIZE_CAP_BYTES = 200 * 1024
MAX_FILES = 10
CHECK_TYPES = ("file_exists", "contains", "regex", "html_element", "no_external_requests")
MODEL_REVIEW = "MODEL_REVIEW"

_PRODUCT_PATH = re.compile(r"^product/(?:[A-Za-z0-9_\-]+/)*[A-Za-z0-9_\-.]+\.(?:html|md|txt|csv|json)$")


def is_product_path(path: str) -> bool:
    return bool(_PRODUCT_PATH.match(path or "")) and ".." not in path


# ------------------------------------------------------------------ simple selectors
_SELECTOR = re.compile(r"^(?P<tag>[a-zA-Z][\w-]*)?(?P<id>#[\w-]+)?(?P<classes>(?:\.[\w-]+)*)(?P<attrs>(?:\[[^\]]+\])*)$")
_ATTR = re.compile(r"\[\s*([\w:-]+)\s*(?:([~^$*]?=)\s*(?:\"([^\"]*)\"|'([^']*)'|([^\]\s\"']*)))?\s*\]")


def parse_selector(selector: str) -> dict[str, Any] | None:
    """Parse one compound selector (tag#id.class[attr=value]). None when unsupported."""
    text = (selector or "").strip()
    match = _SELECTOR.match(text)
    if not text or not match or not any(match.group(g) for g in ("tag", "id", "classes", "attrs")):
        return None
    attr_text = match.group("attrs") or ""
    attrs = []
    consumed = 0
    for am in _ATTR.finditer(attr_text):
        consumed += len(am.group(0))
        value = next((g for g in am.group(3, 4, 5) if g is not None), None)
        attrs.append((am.group(1).lower(), am.group(2), value))
    if consumed != len(attr_text):
        return None
    return {"tag": (match.group("tag") or "").lower() or None,
            "id": (match.group("id") or "")[1:] or None,
            "classes": [c for c in (match.group("classes") or "").split(".") if c],
            "attrs": attrs}


def _attr_matches(op: str | None, expected: str | None, actual: str, name: str) -> bool:
    if op is None:
        return True
    expected = expected or ""
    if name == "type":
        expected, actual = expected.lower(), actual.lower()
    if op == "=":
        return actual == expected
    if op == "*=":
        return expected in actual
    if op == "^=":
        return actual.startswith(expected)
    if op == "$=":
        return actual.endswith(expected)
    if op == "~=":
        return expected in actual.split()
    return False


def element_matches(selector: dict[str, Any], tag: str, attrs: dict[str, str]) -> bool:
    if selector["tag"] and tag != selector["tag"]:
        return False
    if selector["id"] and attrs.get("id") != selector["id"]:
        return False
    classes = (attrs.get("class") or "").split()
    if any(c not in classes for c in selector["classes"]):
        return False
    for name, op, value in selector["attrs"]:
        if name not in attrs or not _attr_matches(op, value, attrs.get(name) or "", name):
            return False
    return True


# ------------------------------------------------------------------ HTML scanning
CRITICAL_TAGS = ("html", "head", "body", "script", "style", "form", "button", "select", "textarea", "table")
_CAPTURE_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "button", "label", "a", "option", "summary", "legend", "th")
_FIELD_TAGS = ("input", "select", "textarea")


class HtmlScan(HTMLParser):
    """Collects elements, tag balance, visible text, scripts, styles and label texts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str]]] = []
        self.counts: dict[str, list[int]] = {}
        self.text: list[str] = []
        self.attr_text: list[str] = []
        self.scripts: list[str] = []
        self.styles: list[str] = []
        self.captured: list[tuple[str, str]] = []      # (tag, text) for headings, buttons, labels, links
        self.labels: list[dict[str, Any]] = []          # {"for": id, "text": str, "fields": [index]}
        self._raw_mode: str | None = None
        self._captures: list[list[Any]] = []
        self._open_labels: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v if v is not None else "") for k, v in attrs}
        self.elements.append((tag, values))
        if tag in CRITICAL_TAGS:
            self.counts.setdefault(tag, [0, 0])[0] += 1
        if tag in ("script", "style"):
            self._raw_mode = tag
        for key in ("placeholder", "alt", "title", "aria-label"):
            if values.get(key):
                self.attr_text.append(values[key])
        if tag == "input" and values.get("type", "").lower() in ("submit", "button") and values.get("value"):
            self.attr_text.append(values["value"])
            self.captured.append(("button", values["value"]))
        if tag in _FIELD_TAGS:
            for label in self._open_labels:
                label["fields"].append(len(self.elements) - 1)
        if tag == "label":
            label = {"for": values.get("for"), "text": [], "fields": []}
            self._open_labels.append(label)
            self.labels.append(label)
        if tag in _CAPTURE_TAGS:
            self._captures.append([tag, []])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # <input/> style: an element that opens and closes at once
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in CRITICAL_TAGS:
            self.counts.setdefault(tag, [0, 0])[1] += 1
        if tag == self._raw_mode:
            self._raw_mode = None
        if tag == "label" and self._open_labels:
            label = self._open_labels.pop()
            label["text"] = " ".join(" ".join(label["text"]).split())
        for i in range(len(self._captures) - 1, -1, -1):
            if self._captures[i][0] == tag:
                name, parts = self._captures.pop(i)
                text = " ".join(" ".join(parts).split())
                if text:
                    self.captured.append((name, text))
                break

    def handle_data(self, data: str) -> None:
        if self._raw_mode == "script":
            self.scripts.append(data)
            return
        if self._raw_mode == "style":
            self.styles.append(data)
            return
        self.text.append(data)
        for label in self._open_labels:
            label["text"].append(data)
        for capture in self._captures:
            capture[1].append(data)

    # --- derived views
    def visible_text(self) -> str:
        return " ".join(" ".join(self.text).split())

    def unclosed(self) -> list[str]:
        return [f"<{tag}> opened {o}x, closed {c}x" for tag, (o, c) in self.counts.items() if o > c]

    def field_label_text(self, index: int) -> str:
        tag, attrs = self.elements[index]
        parts = [str(label["text"]) for label in self.labels
                 if index in label["fields"] or (label["for"] and label["for"] == attrs.get("id"))]
        return " ".join(parts)

    def fields(self) -> list[tuple[int, str, dict[str, str]]]:
        return [(i, tag, attrs) for i, (tag, attrs) in enumerate(self.elements) if tag in _FIELD_TAGS]


def scan_html(content: str) -> tuple[HtmlScan | None, str]:
    scanner = HtmlScan()
    try:
        scanner.feed(content or "")
        scanner.close()
    except Exception as exc:  # noqa: BLE001 - html.parser is lenient; any error is a parse failure
        return None, f"{type(exc).__name__}: {exc}"
    return scanner, ""


# ------------------------------------------------------------------ individual detectors
_REQUEST_ATTRS = ("src", "href", "srcset", "data", "action", "poster", "formaction", "background")
_REQUEST_TAGS = ("script", "link", "img", "iframe", "source", "video", "audio", "embed", "object", "track", "form",
                 "input", "base", "picture", "body", "table", "frame")
_ABSOLUTE = re.compile(r"^\s*(?:https?:)?//", re.I)
_JS_NETWORK = [
    (re.compile(r"(?<![\w$])fetch\s*\(\s*[`'\"](?:https?:)?//", re.I), "fetch() to an absolute URL"),
    (re.compile(r"\.open\s*\(\s*[`'\"][A-Za-z]+[`'\"]\s*,\s*[`'\"](?:https?:)?//", re.I), "XMLHttpRequest to an absolute URL"),
    (re.compile(r"(?<![\w$])fetch\s*\("), "fetch() network call"),
    (re.compile(r"\bXMLHttpRequest\b"), "XMLHttpRequest network call"),
    (re.compile(r"\bnew\s+(?:WebSocket|EventSource)\s*\("), "WebSocket/EventSource connection"),
    (re.compile(r"\bsendBeacon\s*\("), "navigator.sendBeacon call"),
    (re.compile(r"\bimportScripts\s*\("), "importScripts call"),
    (re.compile(r"\bimport\s*\(\s*[`'\"](?:https?:)?//", re.I), "dynamic import from a URL"),
    (re.compile(r"^\s*import\b[^;\n]*\bfrom\s*[`'\"](?:https?:)?//", re.I | re.M), "module import from a URL"),
]
_CSS_NETWORK = re.compile(r"(?:@import\s+(?:url\()?\s*['\"]?|url\(\s*['\"]?)(?:https?:)?//", re.I)


def external_requests(content: str, scanner: HtmlScan | None = None) -> list[str]:
    """Every network request a page would make by itself (links the user clicks are not requests)."""
    scanner = scanner or scan_html(content)[0]
    found: list[str] = []
    if scanner is None:
        return ["page could not be parsed"]
    for tag, attrs in scanner.elements:
        if tag not in _REQUEST_TAGS:
            continue
        for name in _REQUEST_ATTRS:
            value = attrs.get(name) or ""
            if not value:
                continue
            candidates = [part.strip().split(" ")[0] for part in value.split(",")] if name == "srcset" else [value]
            if any(_ABSOLUTE.match(c) for c in candidates):
                found.append(f"<{tag} {name}=\"{value[:80]}\">")
    code = "\n".join(scanner.scripts)
    for tag, attrs in scanner.elements:   # inline event handlers can make requests too
        code += "\n" + "\n".join(v for k, v in attrs.items() if k.startswith("on"))
    seen_kinds: set[str] = set()
    for pattern, label in _JS_NETWORK:
        match = pattern.search(code)
        if match and label.split(" ")[0] not in seen_kinds:
            seen_kinds.add(label.split(" ")[0])
            found.append(f"{label}: {match.group(0)[:60].strip()}")
    styles = "\n".join(scanner.styles) + "\n" + "\n".join(a.get("style", "") for _, a in scanner.elements)
    match = _CSS_NETWORK.search(styles)
    if match:
        found.append(f"CSS loads a remote resource: {match.group(0)[:60]}")
    return found


_SENSITIVE = re.compile(
    r"(?:credit|debit)[\s_-]*card|card[\s_-]*(?:number|no\b|num\b|holder|expir|cvc|cvv|security|details)|cardnumber"
    r"|(?<![a-z])cvv2?(?![a-z])|(?<![a-z])cvc(?![a-z])|(?<![a-z])iban(?![a-z])|(?<![a-z])pass(?:word|wd|code)(?![a-z])"
    r"|routing[\s_-]*number|bank[\s_-]*account|sort[\s_-]*code|(?<![a-z])ssn(?![a-z])|social[\s_-]*security"
    r"|(?<![a-z])cc-(?:number|csc|exp|name|type)", re.I)


def sensitive_fields(scanner: HtmlScan) -> list[str]:
    found = []
    for index, tag, attrs in scanner.fields():
        kind = (attrs.get("type") or "").lower()
        autocomplete = (attrs.get("autocomplete") or "").lower()
        haystack = " ".join([attrs.get("name", ""), attrs.get("id", ""), attrs.get("placeholder", ""),
                             attrs.get("aria-label", ""), autocomplete, attrs.get("title", ""),
                             scanner.field_label_text(index)])
        match = _SENSITIVE.search(haystack)
        if kind == "password" or autocomplete.endswith("password") or autocomplete.startswith("cc-") or match:
            name = attrs.get("name") or attrs.get("id") or kind or tag
            found.append(f"<{tag} {name}>: " + (match.group(0) if match else f"type/autocomplete {kind or autocomplete}"))
    return found


_PERSONAL = re.compile(r"(?<![a-z])(e-?mail|phone|telephone|mobile|street|address|postcode|zip|birth|dob)(?![a-z])", re.I)


def personal_fields(scanner: HtmlScan) -> list[str]:
    found = []
    for index, tag, attrs in scanner.fields():
        kind = (attrs.get("type") or "").lower()
        haystack = " ".join([attrs.get("name", ""), attrs.get("id", ""), attrs.get("autocomplete", ""),
                             scanner.field_label_text(index)])
        if kind in ("email", "tel") or _PERSONAL.search(haystack):
            found.append(f"<{tag} {attrs.get('name') or attrs.get('id') or kind}>")
    return found


def unlabelled_fields(scanner: HtmlScan) -> list[str]:
    found = []
    for index, tag, attrs in scanner.fields():
        kind = (attrs.get("type") or "").lower()
        if kind in ("hidden", "submit", "button", "reset", "image"):
            continue
        if attrs.get("aria-label") or attrs.get("aria-labelledby") or attrs.get("title") or scanner.field_label_text(index).strip():
            continue
        found.append(f"<{tag} {attrs.get('name') or attrs.get('id') or kind or ''}>".replace(" >", ">"))
    return found


_PLACEHOLDER = [re.compile(r"lorem ipsum", re.I), re.compile(r"\bTODO\b"), re.compile(r"\bFIXME\b")]
_SECRETS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
]
_PAYMENT = re.compile(r"\b(stripe|paypal|braintree|paddle\.com|gumroad|lemon ?squeezy|razorpay|squareup)\b"
                      r"|\b(pay now|buy now|checkout|add to cart|enter your card)\b", re.I)
_PAYWALL = re.compile(r"\b(upgrade to (pro|premium|paid)|premium[- ](only|feature)|unlock (all|full|premium|pro)"
                      r"|paid plan required|subscribe to unlock)\b", re.I)
_USAGE_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(usage|how to use|using\b|getting started|quick[\s-]?start)", re.I | re.M)


# ------------------------------------------------------------------ acceptance checks
def run_acceptance_check(check: dict[str, Any], files: dict[str, str]) -> tuple[bool, str]:
    kind = check.get("type")
    name = check.get("file") or INDEX
    value = check.get("value") or ""
    content = files.get(name)
    if kind not in CHECK_TYPES:
        return False, f"unknown check type {kind!r}"
    if content is None or not content.strip():
        return False, f"{name} is missing or empty"
    if kind == "file_exists":
        return True, f"{name} exists ({len(content.encode('utf-8'))} bytes)"
    if kind == "contains":
        ok = value.lower() in content.lower()
        return ok, f"{'found' if ok else 'not found'}: {value[:80]!r} in {name}"
    if kind == "regex":
        try:
            ok = re.search(value, content, re.I | re.M) is not None
        except re.error as exc:
            return False, f"invalid regex {value[:60]!r}: {exc}"
        return ok, f"pattern {value[:80]!r} {'matched' if ok else 'did not match'} in {name}"
    scanner, error = scan_html(content)
    if scanner is None:
        return False, f"{name} could not be parsed: {error}"
    if kind == "html_element":
        selector = parse_selector(value)
        if selector is None:
            return False, f"unsupported selector {value[:60]!r}"
        count = sum(1 for tag, attrs in scanner.elements if element_matches(selector, tag, attrs))
        return count > 0, f"{count} element(s) match {value!r} in {name}"
    requests = external_requests(content, scanner)
    return not requests, ("no network requests found" if not requests else "; ".join(requests[:5]))


# ------------------------------------------------------------------ the full test run
def _result(test_id: str, description: str, critical: bool, passed: bool, detail: str, kind: str,
            feature: str = "") -> dict[str, Any]:
    return {"id": test_id, "description": description, "critical": bool(critical), "passed": bool(passed),
            "detail": detail[:400], "kind": kind, "feature": feature}


def run_checks(files: dict[str, str], acceptance: list[dict[str, Any]], *,
               size_cap: int = SIZE_CAP_BYTES) -> list[dict[str, Any]]:
    """Run every acceptance criterion and every generic check. Deterministic: no model involved."""
    tests: list[dict[str, Any]] = []
    for index, criterion in enumerate(acceptance or [], start=1):
        check = criterion.get("check") or {}
        passed, detail = run_acceptance_check(check, files)
        description = criterion.get("description") or f"{check.get('type')} {check.get('value', '')}".strip()
        tests.append(_result(str(criterion.get("id") or f"AC{index}"), description,
                             criterion.get("critical", True), passed,
                             f"[{check.get('type')} on {check.get('file')}] {detail}", "acceptance",
                             str(criterion.get("feature") or "")))

    index_html = files.get(INDEX) or ""
    readme = files.get(README) or ""
    missing = [name for name in REQUIRED_FILES if not (files.get(name) or "").strip()]
    empty = [name for name, content in files.items() if not (content or "").strip()]
    tests.append(_result("G1", "Required files exist and no file is empty", True, not missing and not empty,
                         "missing: " + ", ".join(missing) if missing else
                         ("empty: " + ", ".join(empty) if empty else f"{len(files)} file(s): " + ", ".join(sorted(files))),
                         "generic"))
    total = sum(len((c or "").encode("utf-8")) for c in files.values())
    bad_paths = [n for n in files if not is_product_path(n)]
    tests.append(_result("G2", f"Total size within {size_cap // 1024} KB, at most {MAX_FILES} files, product/ paths only",
                         True, total <= size_cap and len(files) <= MAX_FILES and not bad_paths,
                         f"{total} bytes in {len(files)} file(s)" + (f"; bad paths: {bad_paths}" if bad_paths else ""),
                         "generic"))

    scanner, error = scan_html(index_html)
    unclosed = scanner.unclosed() if scanner else []
    has_root = scanner is not None and any(tag in ("html", "body") for tag, _ in scanner.elements)
    tests.append(_result("G3", "index.html parses with no unclosed critical tags", True,
                         bool(index_html.strip()) and scanner is not None and not unclosed and has_root,
                         error or ("; ".join(unclosed) if unclosed else
                                   ("no <html> or <body> element" if not has_root else "parsed; critical tags balanced")),
                         "generic"))

    placeholder_hits = []
    for name, content in files.items():
        for pattern in _PLACEHOLDER:
            match = pattern.search(content or "")
            if match:
                placeholder_hits.append(f"{name}: {match.group(0)!r}")
    tests.append(_result("G4", "No placeholder text (lorem ipsum, TODO, FIXME)", True, not placeholder_hits,
                         "; ".join(placeholder_hits) or "none found", "generic"))

    requests = external_requests(index_html, scanner) if index_html.strip() else ["index.html missing"]
    tests.append(_result("G5", "No network requests (external scripts, styles, images, frames, fetch, XHR)", True,
                         not requests, "; ".join(requests[:6]) or "none found", "generic"))

    sensitive = sensitive_fields(scanner) if scanner else []
    tests.append(_result("G6", "No card, CVV, IBAN, bank or password inputs", True, not sensitive,
                         "; ".join(sensitive[:6]) or "none found", "generic"))

    copy_text = ""
    if scanner:
        copy_text = scanner.visible_text() + "\n" + "\n".join(scanner.attr_text) + "\n" + "\n".join(scanner.scripts)
    copy_text += "\n" + readme
    flags = guardrails.check_marketing(copy_text)
    tests.append(_result("G7", "Copy passes the marketing guardrails (no fake proof, urgency or income promises)", True,
                         not flags, "; ".join(f"{v.rule}: '{v.match}'" for v in flags) or "no violations",
                         "generic"))

    tests.append(_result("G8", "product/README.md has a usage section", True, bool(_USAGE_HEADING.search(readme)),
                         "usage heading found" if _USAGE_HEADING.search(readme) else
                         "no '## Usage' (or 'How to use' / 'Getting started') heading", "generic"))

    secret_hits = []
    for name, content in files.items():
        for pattern in _SECRETS:
            match = pattern.search(content or "")
            if match:
                secret_hits.append(f"{name}: {match.group(0)[:12]}...")
    tests.append(_result("G9", "No secrets or keys in the files", True, not secret_hits,
                         "; ".join(secret_hits) or "none found", "generic"))

    product_text = index_html + "\n" + readme
    pay = _PAYMENT.search(product_text)
    wall = _PAYWALL.search(product_text)
    tests.append(_result("G10", "No payments, checkout or paywalled core features", True, not pay and not wall,
                         "; ".join(f"found {m.group(0)!r}" for m in (pay, wall) if m) or "none found", "generic"))

    personal = personal_fields(scanner) if scanner else []
    tests.append(_result("G11", "No personal-data fields (email, phone, address)", False, not personal,
                         "; ".join(personal[:6]) or "none found", "generic"))

    a11y = []
    if scanner:
        html_tags = [a for t, a in scanner.elements if t == "html"]
        if not html_tags or not html_tags[0].get("lang"):
            a11y.append("<html> has no lang attribute")
        if not any(t == "title" for t, _ in scanner.elements):
            a11y.append("no <title>")
        if not any(t == "meta" and (a.get("name") or "").lower() == "viewport" for t, a in scanner.elements):
            a11y.append("no viewport meta tag")
        unlabelled = unlabelled_fields(scanner)
        if unlabelled:
            a11y.append("fields without a label: " + ", ".join(unlabelled[:5]))
    tests.append(_result("G12", "Basic accessibility (lang, title, viewport, labelled fields)", False,
                         scanner is not None and not a11y, "; ".join(a11y) or "all present", "generic"))
    return tests


def is_concrete_bug(bug: dict[str, Any]) -> bool:
    """A model-reported bug counts only if critical/high AND it gives a concrete reproduction."""
    if str(bug.get("severity") or "").lower() not in ("critical", "high"):
        return False
    repro = str(bug.get("reproduction") or "").strip()
    if len(repro) < 20 or re.fullmatch(r"(?i)(n/?a|none|unknown|not applicable|-+|tbd)\.?", repro):
        return False
    return True


def metrics(tests: list[dict[str, Any]], bugs: list[dict[str, Any]]) -> dict[str, Any]:
    critical = [t for t in tests if t["critical"]]
    acceptance = [t for t in tests if t["kind"] == "acceptance"]
    passed_critical = sum(1 for t in critical if t["passed"])
    met = sum(1 for t in acceptance if t["passed"])
    open_bugs = [b for b in bugs if b.get("counts")]
    return {
        "critical_total": len(critical), "critical_passed": passed_critical,
        "critical_pass_rate": round(passed_critical / len(critical), 4) if critical else None,
        "acceptance_total": len(acceptance), "acceptance_met": met,
        "acceptance_met_rate": round(met / len(acceptance), 4) if acceptance else None,
        "open_critical_high_bugs": len(open_bugs),
        "tests_total": len(tests), "tests_passed": sum(1 for t in tests if t["passed"]),
    }


# ------------------------------------------------------------------ inventory of the built UI (for docs)
def ui_inventory(index_html: str) -> dict[str, Any]:
    scanner, _ = scan_html(index_html or "")
    if scanner is None:
        return {"title": "", "headings": [], "buttons": [], "labels": [], "fields": [], "links": [],
                "uses_local_storage": False}

    def texts(*tags: str) -> list[str]:
        out: list[str] = []
        for tag, text in scanner.captured:
            if tag in tags and text not in out:
                out.append(text[:80])
        return out[:30]

    title_match = re.search(r"<title[^>]*>(.*?)</title>", index_html, re.I | re.S)
    fields = []
    for index, tag, attrs in scanner.fields():
        fields.append({"tag": tag, "type": attrs.get("type", ""), "name": attrs.get("name") or attrs.get("id", ""),
                       "label": scanner.field_label_text(index)[:80] or attrs.get("aria-label", "")
                       or attrs.get("placeholder", "")})
    return {"title": " ".join((title_match.group(1) if title_match else "").split())[:120],
            "headings": texts("h1", "h2", "h3", "h4", "h5", "h6", "legend", "summary", "th"),
            "buttons": texts("button"), "labels": texts("label"), "links": texts("a"), "fields": fields[:30],
            "uses_local_storage": "localStorage" in "\n".join(scanner.scripts)}


def searchable_text(index_html: str) -> str:
    """Visible text, attribute text and script strings: where a UI label can come from."""
    scanner, _ = scan_html(index_html or "")
    if scanner is None:
        return index_html or ""
    return "\n".join([scanner.visible_text(), *scanner.attr_text, *scanner.scripts])


# ------------------------------------------------------------------ optional model review
def validate_review(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        data = {"bugs": data}
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object with a 'bugs' list")
    raw = data.get("bugs", data.get("issues", []))
    if not isinstance(raw, list):
        raise ValueError("'bugs' must be a list")
    bugs = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "low").strip().lower()
        if severity not in ("critical", "high", "medium", "low"):
            severity = "low"
        bug = {"id": str(item.get("id") or f"MR{index}")[:20], "title": str(item.get("title") or "")[:200],
               "severity": severity, "reproduction": str(item.get("reproduction") or "")[:600],
               "expected": str(item.get("expected") or "")[:300], "actual": str(item.get("actual") or "")[:300],
               "file": str(item.get("file") or "")[:80], "label": MODEL_REVIEW}
        if bug["title"]:
            bug["counts"] = is_concrete_bug(bug)
            bugs.append(bug)
    return {"bugs": bugs[:15], "summary": str(data.get("summary") or "")[:600]}


def review_build(ctx: StepContext, files: dict[str, str], acceptance: list[dict[str, Any]],
                 tests: list[dict[str, Any]], *, max_chars_per_file: int = 24000) -> dict[str, Any]:
    """Ask a fast model for bugs. Optional: if no model answers, the deterministic tests stand alone."""
    payload = {
        "files": {name: (content if len(content) <= max_chars_per_file
                         else content[:max_chars_per_file] + "\n...(truncated for review)")
                  for name, content in files.items()},
        "acceptance_criteria": [{"id": a.get("id"), "description": a.get("description"), "check": a.get("check")}
                                for a in acceptance],
        "deterministic_results": [{"id": t["id"], "passed": t["passed"], "detail": t["detail"][:160]} for t in tests],
    }
    try:
        data = call_agent(ctx, role=ROLE, task="review_build", payload=payload, tier="fast", max_tokens=2000,
                          validate=validate_review, action_type="RUN_TESTS",
                          description="Model review of the built product (MODEL_REVIEW; deterministic tests stay authoritative)")
    except LLMError as exc:
        return {"bugs": [], "summary": "", "available": False, "note": f"Model review unavailable: {str(exc)[:200]}"}
    data["available"] = True
    data["note"] = ""
    return data


def failures_for_builder(tests: list[dict[str, Any]], bugs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [{"id": t["id"], "description": t["description"], "critical": t["critical"], "detail": t["detail"]}
           for t in tests if not t["passed"]]
    out += [{"id": b["id"], "description": f"{MODEL_REVIEW} bug: {b['title']}", "critical": True,
             "detail": f"reproduction: {b['reproduction']}; expected: {b['expected']}; actual: {b['actual']}"}
            for b in bugs if b.get("counts")]
    return out
