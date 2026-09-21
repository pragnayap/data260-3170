#!/usr/bin/env python3
"""
HW3 Part 2 - build the local document corpus for DOMAIN_ID 2 (Municipal Transit
Incidents).

Downloads public documents from federal sources, snapshots them under
data/corpus/, and writes two provenance files required by the assignment:

    reports/hw03/SOURCES.md          source URL + access date per document
    reports/hw03/CORPUS_MANIFEST.json  filename, byte size, SHA-256 per document

Why a script instead of hand-saved files: the corpus has to be reproducible and
the hashes have to match what was actually retrieved. Running this regenerates
both the snapshots and their provenance in one step, and re-running it verifies
that nothing in data/corpus/ has drifted from its recorded hash.

Sources are all US federal public-domain material about transit safety and
transit incidents:
  * eCFR   - the two regulations governing transit agency safety plans and
             state safety oversight (steady, definitional prose)
  * Federal Register - the rulemakings and the general directive behind them
             (long, argumentative preamble prose with dates and dollar figures)
  * NTSB   - two full accident investigations (narrative prose with dates,
             locations, casualty counts and probable-cause findings)

That mix is deliberate: regulation, rulemaking and incident narrative chunk very
differently, which is the point of the three-way chunking comparison.

Offline / manual fallback:
    If the machine cannot reach these hosts, save the files by hand into
    data/corpus_raw/ using the "manual_filename" of each source below, then run
    this script normally. Anything already present in data/corpus_raw/ is used
    instead of being downloaded -- eCFR pages saved as .html are converted to
    text here, and .txt/.pdf files are copied through untouched. The manifest
    and SOURCES.md come out identical either way.

Usage:
    python fetch_corpus.py              # fetch anything missing, verify the rest
    python fetch_corpus.py --force      # re-download everything
    python fetch_corpus.py --verify     # no network; just re-hash and compare
    python fetch_corpus.py --manual-only  # never touch the network
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
MANUAL_DIR = REPO_ROOT / "data" / "corpus_raw"   # hand-saved originals, if any
REPORT_DIR = REPO_ROOT / "reports" / "hw03"
MANIFEST_PATH = REPORT_DIR / "CORPUS_MANIFEST.json"
SOURCES_PATH = REPORT_DIR / "SOURCES.md"

MIN_CORPUS_BYTES = 200 * 1024  # assignment floor

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) DATA260-HW3-corpus-fetch/1.0"
)

# --- Source list ---------------------------------------------------------
#
# kind:
#   "ecfr_html" - eCFR part page; HTML stripped to text
#   "fr_doc"    - Federal Register document number; the API resolves it to the
#                 plain-text version, so the text we store is the one GPO
#                 publishes rather than our own scrape
#   "pdf"       - saved byte-for-byte; parsed later by the retrieval pipeline

SOURCES: list[dict[str, str]] = [
    {
        "filename": "ecfr_49cfr673_agency_safety_plans.txt",
        "kind": "ecfr_html",
        "url": "https://www.ecfr.gov/current/title-49/subtitle-B/chapter-VI/part-673",
        "manual_filename": "ecfr_part673.html",
        "title": "49 CFR Part 673 - Public Transportation Agency Safety Plans",
        "publisher": "Electronic Code of Federal Regulations (eCFR)",
        "why": "Defines what a transit agency's safety plan must contain, including "
               "the safety risk management and safety assurance processes.",
    },
    {
        "filename": "ecfr_49cfr674_state_safety_oversight.txt",
        "kind": "ecfr_html",
        "url": "https://www.ecfr.gov/current/title-49/subtitle-B/chapter-VI/part-674",
        "manual_filename": "ecfr_part674.html",
        "title": "49 CFR Part 674 - State Safety Oversight",
        "publisher": "Electronic Code of Federal Regulations (eCFR)",
        "why": "Defines how states oversee rail transit safety, including the "
               "accident notification and investigation duties after an incident.",
    },
    {
        "filename": "fr_2024_ptasp_final_rule.txt",
        "kind": "fr_doc",
        "url": "2024-07514",
        "direct_text_url": "https://www.federalregister.gov/documents/full_text/text/2024/04/11/2024-07514.txt",
        "manual_filename": "fr_2024-07514.txt",
        "title": "Public Transportation Agency Safety Plans - Final Rule (2024)",
        "publisher": "Federal Register / Federal Transit Administration",
        "why": "The final rule preamble; long analytical prose with compliance "
               "deadlines and cost estimates.",
    },
    {
        "filename": "fr_2023_ptasp_proposed_rule.txt",
        "kind": "fr_doc",
        "url": "2023-08777",
        "direct_text_url": "https://www.federalregister.gov/documents/full_text/text/2023/04/26/2023-08777.txt",
        "manual_filename": "fr_2023-08777.txt",
        "title": "Public Transportation Agency Safety Plans - Notice of Proposed Rulemaking (2023)",
        "publisher": "Federal Register / Federal Transit Administration",
        "why": "The proposal that preceded the final rule; overlaps it heavily, "
               "which is useful for producing confidently-scored wrong retrievals.",
    },
    {
        "filename": "fr_2024_national_transit_safety_plan.txt",
        "kind": "fr_doc",
        "url": "2024-07392",
        "direct_text_url": "https://www.federalregister.gov/documents/full_text/text/2024/04/10/2024-07392.txt",
        "manual_filename": "fr_2024-07392.txt",
        "title": "National Public Transportation Safety Plan (2024)",
        "publisher": "Federal Register / Federal Transit Administration",
        "why": "National safety performance measures for transit, including the "
               "fatality, injury, safety-event and reliability measures.",
    },
    {
        "filename": "fr_2024_general_directive_24_1_assaults.txt",
        "kind": "fr_doc",
        "url": "2024-21923",
        "direct_text_url": "https://www.federalregister.gov/documents/full_text/text/2024/09/25/2024-21923.txt",
        "manual_filename": "fr_2024-21923.txt",
        "title": "General Directive 24-1: Required Actions Regarding Assaults on Transit Workers",
        "publisher": "Federal Register / Federal Transit Administration",
        "why": "A short, highly specific directive; its requirements appear in no "
               "other document in the corpus.",
    },
    {
        "filename": "ntsb_rir2207_sacramento_light_rail_collision.pdf",
        "kind": "pdf",
        "url": "https://www.ntsb.gov/investigations/AccidentReports/Reports/RIR2207.pdf",
        "manual_filename": "RIR2207.pdf",
        "title": "NTSB/RIR-22/07 - Collision Between Sacramento Regional Transit District Light Rail Vehicles",
        "publisher": "National Transportation Safety Board",
        "why": "A complete single-incident investigation: date, milepost, injury "
               "count and probable cause exist only in this document.",
    },
    {
        "filename": "ntsb_rir2315_wmata_rosslyn_derailment.pdf",
        "kind": "pdf",
        "url": "https://www.ntsb.gov/investigations/AccidentReports/Reports/RIR2315.pdf",
        "manual_filename": "RIR2315.pdf",
        "title": "NTSB/RIR-23/15 - Derailment of Washington Metropolitan Area Transit Authority Train 407",
        "publisher": "National Transportation Safety Board",
        "why": "A second single-incident investigation with a mechanical (rather "
               "than procedural) probable cause, for contrast.",
    },
]


# --- HTML -> text --------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Collect visible text, dropping script/style/nav chrome.

    Deliberately simple: the eCFR part pages are mostly a single column of
    regulatory prose, so tag-stripping plus whitespace normalisation gives clean
    text without pulling in an HTML library.
    """

    SKIP = {"script", "style", "noscript", "svg", "head"}
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag in self.BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BLOCK:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip() + "\n"


# --- Fetching ------------------------------------------------------------

def http_get(url: str, accept: str = "*/*") -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def html_to_text(html: str) -> bytes:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text().encode("utf-8")


# eCFR part pages carry a lot of site furniture -- a browser warning, the
# breadcrumb nav, and a long footer of links. Left in, every one of those
# becomes chunks that compete with the regulation itself during retrieval, so
# the text is cut down to the regulation between these two landmarks.
ECFR_START_RE = re.compile(r"^PART\s+\d+[^\n]*$", re.MULTILINE)
ECFR_END_MARKERS = ("\neCFR Content\n", "\nPages\nHome\nTitles\n")


def trim_ecfr_chrome(text: str) -> str:
    """Drop the eCFR site header and footer, keeping the regulatory text."""
    start = ECFR_START_RE.search(text)
    if start:
        text = text[start.start():]

    for marker in ECFR_END_MARKERS:
        index = text.rfind(marker)
        if index > len(text) // 2:   # only cut a marker in the trailing region
            text = text[:index]
            break
    return text.strip() + "\n"


# A browser "Save Page As" on a Federal Register plain-text URL wraps the text
# in <html><head><title>..</title></head><body><pre>. The bytes are right, the
# container is not. The network path never hits this; the manual path always
# does, so unwrap it rather than asking for a different save format.
FR_PRE_RE = re.compile(r"<pre>(.*?)</pre>", re.IGNORECASE | re.DOTALL)


def unwrap_federal_register(payload: bytes) -> bytes:
    """Return the plain text inside a browser-saved Federal Register page."""
    text = payload.decode("utf-8", errors="replace").replace("\x00", "")
    if "<html" not in text[:200].lower():
        return text.encode("utf-8")       # already plain text

    match = FR_PRE_RE.search(text)
    inner = match.group(1) if match else text

    # GPO leaves its own markup inside the <pre>: <a href=..> around cross
    # references, <bullet>, <span>. Dropping the tags keeps the anchor text and
    # loses the URLs, which would otherwise be embedded as if they were prose.
    inner = re.sub(r"<[^>]+>", "", inner)
    inner = html.unescape(inner)
    inner = re.sub(r"[ \t]+\n", "\n", inner)
    inner = re.sub(r"\n{3,}", "\n\n", inner)
    return (inner.strip() + "\n").encode("utf-8")


def fetch_ecfr(url: str) -> bytes:
    raw = http_get(url, accept="text/html").decode("utf-8", errors="replace")
    return trim_ecfr_chrome(html_to_text(raw).decode("utf-8")).encode("utf-8")


def load_manual(source: dict) -> bytes | None:
    """Use a hand-saved original from data/corpus_raw/ if one is sitting there.

    eCFR pages are saved as HTML by a browser, so they get the same tag-strip
    the network path applies; .txt and .pdf are byte-identical copies. This is
    what makes the corpus reproducible on a machine with no route to these
    hosts.
    """
    name = source.get("manual_filename")
    if not name:
        return None
    candidate = MANUAL_DIR / name
    if not candidate.exists():
        return None

    print(f"        using hand-saved original data/corpus_raw/{name}")

    if source["kind"] == "ecfr_html":
        raw = candidate.read_text(encoding="utf-8", errors="replace")
        return trim_ecfr_chrome(html_to_text(raw).decode("utf-8")).encode("utf-8")

    if source["kind"] == "fr_doc":
        return unwrap_federal_register(candidate.read_bytes())

    return candidate.read_bytes()


def fetch_federal_register(document_number: str, fallback_url: str | None = None) -> tuple[bytes, str]:
    """Resolve an FR document number to its plain-text version and download it.

    Returns (content, resolved_url) so SOURCES.md can record the URL that was
    actually retrieved rather than the bare document number.
    """
    api = (
        f"https://www.federalregister.gov/api/v1/documents/{document_number}.json"
        "?fields[]=raw_text_url&fields[]=title&fields[]=publication_date&fields[]=html_url"
    )
    try:
        meta = json.loads(http_get(api, accept="application/json").decode("utf-8"))
        raw_url = meta.get("raw_text_url")
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"        API lookup failed ({exc}); falling back to the recorded text URL")
        raw_url = fallback_url
    if not raw_url:
        raise RuntimeError(f"FR document {document_number} has no raw_text_url")
    return http_get(raw_url, accept="text/plain"), raw_url


def fetch_pdf(url: str) -> bytes:
    return http_get(url, accept="application/pdf")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- Main ----------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download everything")
    parser.add_argument("--verify", action="store_true",
                        help="no network; re-hash local files against the manifest")
    parser.add_argument("--manual-only", action="store_true",
                        help="never use the network; require data/corpus_raw/ originals")
    args = parser.parse_args()

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.verify:
        return verify_against_manifest()

    today = dt.date.today().isoformat()
    entries: list[dict] = []
    failures: list[str] = []

    for source in SOURCES:
        target = CORPUS_DIR / source["filename"]
        resolved_url = source["url"]

        if target.exists() and not args.force:
            print(f"[skip]  {source['filename']}  (already present, {target.stat().st_size:,} bytes)")
        else:
            print(f"[fetch] {source['filename']}  <- {source['url']}")
            try:
                payload = load_manual(source)
                if payload is not None:
                    resolved_url = f"data/corpus_raw/{source['manual_filename']} (hand-saved)"
                elif args.manual_only:
                    raise RuntimeError(
                        f"--manual-only, but data/corpus_raw/{source.get('manual_filename')} is missing"
                    )
                elif source["kind"] == "ecfr_html":
                    payload = fetch_ecfr(source["url"])
                elif source["kind"] == "fr_doc":
                    payload, resolved_url = fetch_federal_register(
                        source["url"], source.get("direct_text_url")
                    )
                    payload = unwrap_federal_register(payload)
                elif source["kind"] == "pdf":
                    payload = fetch_pdf(source["url"])
                else:
                    raise RuntimeError(f"unknown kind {source['kind']!r}")
            except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as exc:
                print(f"        !! FAILED: {exc}")
                failures.append(f"{source['filename']}: {exc}")
                continue

            if len(payload) < 2000:
                print(f"        !! suspiciously small ({len(payload)} bytes) -- not saved")
                failures.append(f"{source['filename']}: only {len(payload)} bytes")
                continue

            target.write_bytes(payload)
            print(f"        saved {len(payload):,} bytes")

        # Keep an already-recorded access date rather than stamping today on a skip.
        previous = _previous_entry(source["filename"])
        entries.append(
            {
                "filename": source["filename"],
                "title": source["title"],
                "publisher": source["publisher"],
                "source_url": source["url"] if source["kind"] != "fr_doc"
                              else f"https://www.federalregister.gov/d/{source['url']}",
                "retrieved_url": resolved_url,
                "access_date": previous.get("access_date", today) if target.exists() and not args.force else today,
                "media_type": "application/pdf" if source["kind"] == "pdf" else "text/plain",
                "bytes": target.stat().st_size,
                "sha256": sha256_of(target),
                "why_included": source["why"],
            }
        )

    total = sum(e["bytes"] for e in entries)
    write_manifest(entries, total)
    write_sources_md(entries, total)

    print()
    print(f"corpus documents : {len(entries)}")
    print(f"corpus size      : {total:,} bytes ({total / 1024:.1f} KB)")
    print(f"assignment floor : {MIN_CORPUS_BYTES:,} bytes (200.0 KB)")
    print(f"manifest         : {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    print(f"sources          : {SOURCES_PATH.relative_to(REPO_ROOT)}")

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    if total < MIN_CORPUS_BYTES:
        print("\nFAIL: corpus is under the 200 KB floor.")
        return 1
    print("\nOK: corpus complete and over the 200 KB floor.")
    return 0


def _previous_entry(filename: str) -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        data = json.loads(MANIFEST_PATH.read_text())
    except json.JSONDecodeError:
        return {}
    for entry in data.get("documents", []):
        if entry.get("filename") == filename:
            return entry
    return {}


def write_manifest(entries: list[dict], total: int) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "corpus_name": "Municipal Transit Incidents (DOMAIN_ID 2)",
                "prefix": "s3170",
                "generated_by": "code/fetch_corpus.py",
                "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "corpus_dir": "data/corpus",
                "document_count": len(entries),
                "total_bytes": total,
                "total_kb": round(total / 1024, 1),
                "minimum_required_bytes": MIN_CORPUS_BYTES,
                "meets_minimum": total >= MIN_CORPUS_BYTES,
                "hash_algorithm": "sha256",
                "documents": entries,
            },
            indent=2,
        )
        + "\n"
    )


def write_sources_md(entries: list[dict], total: int) -> None:
    lines = [
        "# Corpus Sources - Municipal Transit Incidents (DOMAIN_ID 2)",
        "",
        f"**Documents:** {len(entries)}  |  **Total size:** {total:,} bytes "
        f"({total / 1024:.1f} KB)  |  **Minimum required:** 200 KB",
        "",
        "All documents are US federal government publications in the public domain.",
        "Local snapshots live in `data/corpus/`; byte sizes and SHA-256 hashes are in",
        "`reports/hw03/CORPUS_MANIFEST.json`. Re-run `python code/fetch_corpus.py --verify`",
        "to confirm the local files still match their recorded hashes.",
        "",
        "## How these snapshots were obtained",
        "",
        "`code/fetch_corpus.py` builds the corpus. It downloads each document, converts",
        "it to text, and writes this file plus the manifest in one step.",
        "",
        "Any entry whose **Retrieved from** line reads *(hand-saved)* was downloaded in a",
        "browser into `data/corpus_raw/` and converted by the same code path rather than",
        "fetched over the network. The two routes produce identical output: eCFR pages are",
        "tag-stripped and trimmed to the regulation either way, Federal Register documents",
        "are unwrapped from the browser's HTML container, and PDFs are copied byte for byte.",
        "`data/corpus_raw/` holds those originals and is not tracked in git; `data/corpus/`",
        "is the corpus the pipeline reads.",
        "",
        "Reproduce with `python code/fetch_corpus.py` (network) or",
        "`python code/fetch_corpus.py --manual-only` (from `data/corpus_raw/`), then",
        "`python code/fetch_corpus.py --verify` to confirm the hashes below.",
        "",
    ]
    for entry in entries:
        lines += [
            f"## {entry['title']}",
            "",
            f"- **Local file:** `data/corpus/{entry['filename']}`",
            f"- **Publisher:** {entry['publisher']}",
            f"- **Source URL:** {entry['source_url']}",
            f"- **Retrieved from:** {entry['retrieved_url']}",
            f"- **Access date:** {entry['access_date']}",
            f"- **Size:** {entry['bytes']:,} bytes",
            f"- **SHA-256:** `{entry['sha256']}`",
            f"- **Why it is in the corpus:** {entry['why_included']}",
            "",
        ]
    SOURCES_PATH.write_text("\n".join(lines))


def verify_against_manifest() -> int:
    if not MANIFEST_PATH.exists():
        print("No manifest yet -- run without --verify first.")
        return 1

    data = json.loads(MANIFEST_PATH.read_text())
    bad = 0
    for entry in data["documents"]:
        path = CORPUS_DIR / entry["filename"]
        if not path.exists():
            print(f"MISSING  {entry['filename']}")
            bad += 1
            continue
        actual = sha256_of(path)
        if actual != entry["sha256"]:
            print(f"CHANGED  {entry['filename']}\n         recorded {entry['sha256']}\n"
                  f"         actual   {actual}")
            bad += 1
        else:
            print(f"OK       {entry['filename']}  {entry['bytes']:,} bytes")

    print(f"\n{len(data['documents']) - bad}/{len(data['documents'])} documents match the manifest.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
