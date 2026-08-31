import argparse, json, os, re, sys, time
from dataclasses import dataclass
from typing import List, Dict, Any, Iterable, Tuple

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


STOP = {
    "the", "and", "for", "that", "with", "this", "from", "into", "than", "your", "you",
    "are", "was", "were", "have", "has", "had", "use", "used", "using", "about", "how",
    "can", "will", "more", "less", "very", "over", "under", "their", "there", "then",
    "our", "out", "on", "in", "of", "to", "by", "a", "an", "is", "it", "as",
}


# -------------------------
# Text cleanup + extraction
# -------------------------

def strip_code_and_md(s: str) -> str:
    """Remove markdown/code artifacts from model output and normalize whitespace."""
    s = str(s)
    s = re.sub(r"```.*?```", " ", s, flags=re.DOTALL)  # fenced code blocks
    s = s.replace("`", "")  # inline backticks
    s = re.sub(r"[*_#>]+", "", s)  # bold/italic/heading/quote markers
    return " ".join(s.split())


def extract_json_block(text: str) -> str:
    """Extract the first balanced JSON object from a text response.

    Handles responses wrapped in ```json ... ``` fences and responses with
    extra prose before/after the JSON. Falls back to wrapping the cleaned
    text as {"message": "..."} if no JSON object is found.
    """
    text = str(text).strip()

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1)

    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

    return json.dumps({"message": strip_code_and_md(text)})


def tokens(txt: str) -> List[str]:
    """Lowercase word tokens (letters and internal hyphens only)."""
    return re.findall(r"[a-z][a-z\-]+", str(txt).lower())


def ngrams(words: List[str], n: int) -> Iterable[Tuple[str, ...]]:
    """Yield word n-grams from a token list."""
    for i in range(max(0, len(words) - n + 1)):
        yield tuple(words[i:i + n])


def phrase_candidates(title: str, content: str, maxn: int = 12) -> List[str]:
    """Build tag candidates derived ONLY from title+content.

    Tokenizes, removes stop words, ranks bigrams/trigrams by frequency,
    then fills any remaining slots with the most frequent unigrams.
    """
    from collections import Counter

    words = [w for w in tokens(f"{title} {content}") if w not in STOP and len(w) > 2]

    phrase_counts: Counter = Counter()
    for n in (3, 2):
        for gram in ngrams(words, n):
            phrase_counts[" ".join(gram)] += 1

    ranked = [phrase for phrase, _ in phrase_counts.most_common(maxn)]

    if len(ranked) < maxn:
        for word, _ in Counter(words).most_common():
            if word not in ranked:
                ranked.append(word)
            if len(ranked) >= maxn:
                break

    return ranked[:maxn]


# -------------------------
# Output schema coercion
# -------------------------

def _truncate_words(s: str, max_words: int) -> str:
    words = s.split()
    return s if len(words) <= max_words else " ".join(words[:max_words])


def coerce_reply(raw_obj: Any, title: str, content: str, strict: bool) -> Dict[str, Any]:
    """Coerce arbitrary model output into the required schema:
      {
        "thought": str,
        "message": str (non-empty, <= 60 words),
        "data": {
          "tags": [str, str, str],        # exactly 3 topical tags
          "summary": str,                # <= 25 words, ends with '.'
          "issues": [str, ...]
        }
      }

    strict=True enforces at least two multi-word tags, pulling replacements
    from the title/content-derived phrase candidates if the model's tags
    don't satisfy that.
    """
    if not isinstance(raw_obj, dict):
        raw_obj = {}

    thought = strip_code_and_md(str(raw_obj.get("thought", "")))

    message = strip_code_and_md(str(raw_obj.get("message", "")))
    if not message:
        message = "OK — proposal reviewed; tags and summary prepared."
    message = _truncate_words(message, 60)

    data = raw_obj.get("data", {})
    if not isinstance(data, dict):
        data = {}

    # --- tags: exactly 3, deduped, topical (derived from title/content) ---
    raw_tags = data.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = []
    tags: List[str] = []
    for t in raw_tags:
        t = strip_code_and_md(str(t)).strip().lower()
        if t and t not in tags:
            tags.append(t)

    fallback_pool = [c for c in phrase_candidates(title, content, maxn=12) if c not in tags]

    if strict:
        multiword_count = sum(1 for t in tags if " " in t)
        pool_multiword = [c for c in fallback_pool if " " in c]
        i = 0
        while multiword_count < 2 and i < len(pool_multiword):
            tags.append(pool_multiword[i])
            multiword_count += 1
            i += 1
        fallback_pool = [c for c in fallback_pool if c not in tags]

    for candidate in fallback_pool:
        if len(tags) >= 3:
            break
        tags.append(candidate)

    while len(tags) < 3:
        tags.append(f"topic {len(tags) + 1}")

    tags = tags[:3]

    # --- summary: <=25 words, ends with '.' ---
    summary = strip_code_and_md(str(data.get("summary", ""))).strip()
    if not summary:
        summary = strip_code_and_md(content)
    summary = _truncate_words(summary, 25).rstrip(".") + "."

    # --- issues: list of strings ---
    raw_issues = data.get("issues", [])
    if not isinstance(raw_issues, list):
        raw_issues = [raw_issues] if raw_issues else []
    issues = [strip_code_and_md(str(i)) for i in raw_issues if str(i).strip()]

    return {
        "thought": thought,
        "message": message,
        "data": {"tags": tags, "summary": summary, "issues": issues},
    }


def parse_and_coerce(text: str, title: str, content: str, strict: bool) -> Dict[str, Any]:
    """Extract JSON from raw model text, then coerce it into the required schema."""
    try:
        obj = json.loads(extract_json_block(text))
    except Exception:
        obj = {"message": strip_code_and_md(text)}
    return coerce_reply(obj, title, content, strict)


# -------------------------
# Agent wrapper
# -------------------------

@dataclass
class SimpleAgent:
    name: str
    system: str
    model: Any  # LangChain ChatModel

    def respond(
        self,
        conversation: List[Dict[str, str]],
        task: str,
        title: str,
        content: str,
        strict: bool,
    ) -> Dict[str, Any]:
        """Run the prompt chain and coerce the output into the required schema."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system),
            ("human",
             "Task:\n{task}\n\nConversation so far:\n{history}\n\n"
             "Return ONLY one JSON object (no code fences, no markdown, no explanations). "
             "Keys: thought (string), message (non-empty, <=60 words, no code), "
             "data.tags (array of exactly 3 topical tags), "
             "data.summary (<=25 words, no ellipses), data.issues (array).\n"
             "Do not add extra text outside JSON."
            ),
        ])

        history_text = "\n".join([f'{m["role"]}: {m["content"]}' for m in conversation]) or "(empty)"
        chain = prompt | self.model | StrOutputParser()

        raw = chain.invoke({"task": task, "history": history_text})
        return parse_and_coerce(raw, title, content, strict)


# -------------------------
# Shared pipeline (used by both the CLI below and run_nondeterminism.py)
# -------------------------

def make_llm(model: str, temperature: float, base_url: str) -> ChatOllama:
    return ChatOllama(
        model=model,
        temperature=temperature,
        base_url=base_url,
        num_ctx=2048,
        reasoning=False,  # Qwen3 "thinking" mode adds huge latency; disable for this pipeline
        format="json",  # asks Ollama to produce JSON when supported
    )


def build_agents(llm: ChatOllama) -> Tuple[SimpleAgent, SimpleAgent, SimpleAgent]:
    planner = SimpleAgent(
        name="Planner",
        system="Propose exactly 3 distinct, topical tags (prefer multi-word phrases) and a one-line summary for the input.",
        model=llm,
    )
    reviewer = SimpleAgent(
        name="Reviewer",
        system=(
            "Validate: tags topical and not generic; summary ≤ 25 words; no code or markdown. "
            "If issues, list in data.issues; otherwise echo cleaned tags/summary."
        ),
        model=llm,
    )
    finalizer = SimpleAgent(
        name="Finalizer",
        system=(
            "Use reviewer feedback to finalize. Output exactly 3 tags in data.tags and the final summary in data.summary. "
            "Set data.issues to []."
        ),
        model=llm,
    )
    return planner, reviewer, finalizer


def run_pipeline(
    planner: SimpleAgent,
    reviewer: SimpleAgent,
    finalizer: SimpleAgent,
    title: str,
    content: str,
    email: str = "student@example.com",
    strict: bool = False,
) -> Dict[str, Any]:
    """Run one full Planner -> Reviewer -> Finalizer pass.

    Returns a dict with the transcript, each stage's timing (ms), and the
    final coerced output (exactly 3 tags + summary).
    """
    task = (
        f'Given input title "{title}" and content "{content}", produce exactly 3 topical tags '
        f'and a one-sentence summary in your own words. Email is {email}.'
    )

    transcript: List[Dict[str, str]] = []
    timings_ms: Dict[str, int] = {}

    t0 = time.time()
    a = planner.respond(transcript, task, title, content, strict)
    timings_ms["planner"] = int((time.time() - t0) * 1000)
    transcript.append({"role": "Planner", "content": a.get("message", "")})

    t0 = time.time()
    b = reviewer.respond(transcript, task, title, content, strict)
    timings_ms["reviewer"] = int((time.time() - t0) * 1000)
    transcript.append({"role": "Reviewer", "content": b.get("message", "")})

    t0 = time.time()
    final = finalizer.respond(transcript, task, title, content, strict)
    timings_ms["finalizer"] = int((time.time() - t0) * 1000)

    timings_ms["total"] = timings_ms["planner"] + timings_ms["reviewer"] + timings_ms["finalizer"]

    return {
        "planner": a,
        "reviewer": b,
        "final": final,
        "transcript": transcript,
        "timings_ms": timings_ms,
    }


# -------------------------
# CLI entrypoint
# -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="Your Input Title Here")
    ap.add_argument("--content", default="Your input content goes here.")
    ap.add_argument("--email", default="student@example.com")
    ap.add_argument("--model", default=os.environ.get("SMOL_MODEL", "qwen3:8b"))
    ap.add_argument("--base_url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    try:
        llm = make_llm(args.model, args.temperature, args.base_url)
    except Exception:
        print(
            "Failed to initialize ChatOllama. Is Ollama running and the model available?\n"
            "Try: `ollama serve` and `ollama pull <your-model-tag>`.",
            file=sys.stderr,
        )
        raise

    planner, reviewer, finalizer = build_agents(llm)
    result = run_pipeline(planner, reviewer, finalizer, args.title, args.content, args.email, args.strict)

    print(f"\n--- Planner ({result['timings_ms']['planner']} ms) ---\n{json.dumps(result['planner'], indent=2)}")
    print(f"\n--- Reviewer ({result['timings_ms']['reviewer']} ms) ---\n{json.dumps(result['reviewer'], indent=2)}")
    print(f"\n Finalized Output \n{json.dumps(result['final'], indent=2)}")

    package = {
        "title": args.title,
        "email": args.email,
        "content": args.content,
        "agents": {"transcript": result["transcript"], "final": result["final"].get("data", {})},
        "submissionDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print(f"\n Publish Package \n{json.dumps(package, indent=2)}")


if __name__ == "__main__":
    main()
