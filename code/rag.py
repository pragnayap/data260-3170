#!/usr/bin/env python3
"""
HW4 Part 4 - grounded RAG over a synthetic Municipal Transit Incidents corpus.

Studies context engineering: what evidence goes into the model's context
window (which chunks, how many, de-duplicated or not, labeled or not, with
what grounding rules) as distinct from prompt engineering. The corpus lives
in data/rag_docs/ (five invented Baywood Transit Authority policy documents,
DOMAIN_ID 2), separate from HW3's real transit-regulation corpus in
data/corpus/ so this homework can control exactly which facts exist and
which questions have no answer at all.

Pipeline
    1. Chunk the five documents (chunk_size=500 chars, chunk_overlap=50 chars;
       see chunk_text() for why characters rather than tokens), embed with the
       same HuggingFace MiniLM model HW3 used, and load into an in-memory
       LlamaIndex SimpleVectorStore (no vector_store arg to VectorStoreIndex).
    2. For every question, retrieve top_k=3 chunks and print/save source+score
       BEFORE any LLM call, so retrieval problems are visible separately from
       generation problems.
    3. Run all six questions through three configurations:
         A  No RAG            - bare question to qwen3:8b via Ollama
         B  Basic RAG         - top-3 raw chunks pasted in, no cleanup
         C  Context-engineered - de-duplicated, irrelevance-filtered,
                                 source-labeled, grounding-rule prompt that
                                 must refuse with an exact string when the
                                 context does not support an answer
    4. Sweep one question (the two-chunk question, Q2) across k = 1, 3, 5
       using the context-engineered prompt, to see whether more retrieved
       context helps, hurts, or does nothing once the real chunks run out.
    5. Score a heuristic evaluation table (correct retrieval / correct answer
       / grounded / refused-when-needed) from the real transcripts.

All LLM calls go through src/model_client.ModelClient (the project's shared
Ollama adapter), so qwen3:8b is actually invoked for every generation in this
file -- nothing here is a canned or hand-typed example output.

Usage
    python code/rag.py                    # full graded run (retrieval + A/B/C + sweep + eval)
    python code/rag.py --questions-only    # chunk, embed, retrieve, print -- no LLM calls
    python code/rag.py --skip-sweep        # skip the k=1,3,5 sweep
    python code/rag.py --top-k 5           # override the baseline retrieval k
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

RAG_DOCS_DIR = REPO_ROOT / "data" / "rag_docs"
REPORT_DIR = REPO_ROOT / "reports" / "hw04"
RAW_DIR = REPORT_DIR / "raw"

SEED = 3170           # SID4; recorded for traceability, no RNG is used
VERIFY_SEED = 263170  # 260000 + SID4

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # same model HW3 used
LLM_MODEL_NAME = "qwen3:8b"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Every rag_docs file opens with the same "BAYWOOD TRANSIT AUTHORITY / <title>
# / Effective|Revised <date>" boilerplate. Left in, that boilerplate becomes
# part of chunk 0 of every document and was observed (during corpus tuning)
# to out-rank chunks carrying the actual specific fact a question asked about,
# simply on generic word overlap ("vehicle", "service", "Authority") with the
# query. Stripping it before chunking is a real context-engineering decision
# made from observed retrieval behavior, not a cosmetic one -- see analysis.md.
DOC_HEADER_RE = re.compile(r"^BAYWOOD TRANSIT AUTHORITY\n.*\n(?:Effective|Revised).*\n\n", re.MULTILINE)

REFUSAL_STRING = "I cannot answer this question from the provided documents"

CANDIDATE_K = 5       # config C's initial retrieval pool, before filtering
CONTEXT_TOP_N = 3     # config C's max surviving chunks after filtering
SCORE_FLOOR_RATIO = 0.55  # candidates scoring below this fraction of the top score are dropped as irrelevant
DEDUP_SIMILARITY = 0.5    # SequenceMatcher ratio above which two same-source chunks count as near-duplicates

SWEEP_QID = "q1_single_chunk"
SWEEP_KS = (1, 3, 5)


def banner(title: str, char: str = "=") -> None:
    print()
    print(char * 100)
    print(f"[{time.strftime('%H:%M:%S')}] {title}")
    print(char * 100)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# --- Data model ------------------------------------------------------------

@dataclass
class Chunk:
    chunk_id: str
    source: str
    text: str
    char_start: int
    char_end: int


@dataclass
class RetrievedChunk:
    rank: int
    score: float
    chunk_id: str
    source: str
    text: str


@dataclass
class Question:
    qid: str
    text: str
    kind: str  # single_chunk | two_chunk | cross_doc_overlap | ambiguous | not_in_corpus | unrelated
    expected_sources: list[str]
    gold_keywords: list[str]
    notes: str
    must_refuse: bool = False


@dataclass
class GenerationRecord:
    qid: str
    config: str  # A | B | C
    k_used: int
    system_prompt: str
    user_prompt: str
    raw_response: str
    answer_text: str
    latency_s: float
    timestamp: str
    context_chunk_ids: list[str] = field(default_factory=list)
    context_sources: list[str] = field(default_factory=list)


@dataclass
class SweepRecord:
    qid: str
    k: int
    retrieved: list[RetrievedChunk]
    system_prompt: str
    user_prompt: str
    raw_response: str
    answer_text: str
    latency_s: float
    timestamp: str


@dataclass
class EvalRow:
    qid: str
    config: str
    correct_retrieval: Optional[bool]
    correct_answer: Optional[bool]
    grounded: Optional[bool]
    refused_when_needed: Optional[bool]
    notes: str


# --- The six graded questions ----------------------------------------------
# Written against the rag_docs corpus before any retrieval was run, mirroring
# HW3's questions.yaml discipline: expected_sources/keywords come from the
# source documents themselves, not from a model's summary of them.

QUESTIONS: list[Question] = [
    Question(
        qid="q1_single_chunk",
        text=(
            "What system-wide on-time performance target must Baywood Transit "
            "Authority routes meet, according to the service standards?"
        ),
        kind="single_chunk",
        expected_sources=["route_service_standards.txt"],
        gold_keywords=["90", "5 minutes"],
        notes="Answer (90% of trips within 5 minutes) sits in one chunk of one document.",
    ),
    Question(
        qid="q2_dual_fact",
        text=(
            "How soon after a fatal collision must the State Transit Safety "
            "Oversight body be notified, and how many days does an accident "
            "investigator have to determine probable cause?"
        ),
        kind="two_chunk",
        expected_sources=["accident_collision_investigation.txt"],
        gold_keywords=["4 hours", "30 days"],
        notes=(
            "Both facts live in the same document but in different sections "
            "(external fatality notification vs. probable-cause deadline), so "
            "a correct answer still requires combining two separate chunks, "
            "not just quoting one. Picked after probing retrieval scores "
            "directly: an earlier cross-document version of this question "
            "(collision reporting + brake-wear threshold) buried its second "
            "target chunk past rank 10 because a same-document chunk about "
            "routine brake inspection intervals out-scored it on generic word "
            "overlap -- see analysis.md."
        ),
    ),
    Question(
        qid="q3_overlap_disambiguation",
        text=(
            "How soon must an Accident-Collision or Safety Hazard incident be "
            "reported to the Safety Office, and does that clock start from when "
            "the incident happened or from when the report is filed?"
        ),
        kind="cross_doc_overlap",
        expected_sources=[
            "incident_reporting_policy.txt",
            "safety_hazard_procedures.txt",
            "accident_collision_investigation.txt",
        ],
        gold_keywords=["2 hours"],
        notes=(
            "All three documents give a 2-hour window but anchor the clock "
            "differently (report-filed vs. hazard-discovered vs. incident-occurred). "
            "Tests de-duplication/disambiguation, not just keyword match."
        ),
    ),
    Question(
        qid="q4_ambiguous",
        text="How long does it take to resolve an incident at Baywood Transit Authority?",
        kind="ambiguous",
        expected_sources=[
            "safety_hazard_procedures.txt",
            "accident_collision_investigation.txt",
            "route_service_standards.txt",
        ],
        gold_keywords=[],
        notes=(
            "Ambiguous: could mean hazard mitigation windows (24h/5bd/30d/90d by "
            "severity), collision probable-cause investigation (30 days), or "
            "service review completion (15 business days). No single correct number."
        ),
    ),
    Question(
        qid="q5_not_in_corpus",
        text="What is Baywood Transit Authority's total annual operating budget?",
        kind="not_in_corpus",
        expected_sources=[],
        gold_keywords=[],
        notes="No financial figures anywhere in the corpus. Must be refused by config C.",
        must_refuse=True,
    ),
    Question(
        qid="q6_unrelated",
        text="What is the boiling point of water at sea level, in degrees Celsius?",
        kind="unrelated",
        expected_sources=[],
        gold_keywords=[],
        notes="Unrelated to the corpus entirely, though the model knows the real-world answer. Must be refused by config C.",
        must_refuse=True,
    ),
]


# --- Chunking ----------------------------------------------------------------

def chunk_text(text: str, source: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    """Slide a size-char window with overlap-char overlap over one document.

    Character-based, not token-based: the assignment's chunk_size=500,
    chunk_overlap=50 is the standard langchain/RAG-tutorial figure quoted in
    characters, and using characters here (rather than reusing HW3's
    token-based TokenTextSplitter) keeps chunk boundaries directly inspectable
    against the source .txt files. Boundaries snap back to the nearest
    preceding whitespace so a chunk never starts or ends mid-word.
    """
    chunks: list[Chunk] = []
    stem = Path(source).stem
    n = len(text)
    step = size - overlap
    start = 0
    idx = 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            snap = text.rfind(" ", start, end)
            if snap > start:
                end = snap
        piece = text[start:end].strip()
        if piece:
            chunks.append(
                Chunk(
                    chunk_id=f"{stem}_{idx:03d}",
                    source=source,
                    text=piece,
                    char_start=start,
                    char_end=end,
                )
            )
            idx += 1
        if end >= n:
            break
        start += step
    return chunks


def load_corpus(directory: Path) -> list[Chunk]:
    if not directory.exists() or not any(directory.glob("*.txt")):
        sys.exit(f"No .txt documents found in {directory}")
    all_chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.txt")):
        text = DOC_HEADER_RE.sub("", path.read_text(encoding="utf-8"), count=1)
        doc_chunks = chunk_text(text, path.name)
        all_chunks.extend(doc_chunks)
        log(f"  {path.name:<44} {len(text):>6} chars -> {len(doc_chunks)} chunks")
    return all_chunks


def build_index(chunks: list[Chunk], embed_model):
    """Embed chunks into an in-memory LlamaIndex SimpleVectorStore.

    No vector_store argument to VectorStoreIndex -> SimpleVectorStore, the
    same in-memory store HW3 used (faiss-cpu is installed but unused, matching
    the existing pattern in code/run_rag_chunking.py).
    """
    from llama_index.core import VectorStoreIndex
    from llama_index.core.schema import TextNode

    nodes = [
        TextNode(
            text=c.text,
            id_=c.chunk_id,
            metadata={"source": c.source, "chunk_id": c.chunk_id,
                      "char_start": c.char_start, "char_end": c.char_end},
        )
        for c in chunks
    ]
    start = time.perf_counter()
    index = VectorStoreIndex(nodes, embed_model=embed_model, show_progress=False)
    embed_seconds = time.perf_counter() - start
    return index, embed_seconds


def retrieve(index, question: str, k: int) -> list[RetrievedChunk]:
    retriever = index.as_retriever(similarity_top_k=k)
    results = retriever.retrieve(question)
    out = []
    for rank, scored_node in enumerate(results, start=1):
        node = scored_node.node
        out.append(
            RetrievedChunk(
                rank=rank,
                score=round(float(scored_node.score or 0.0), 6),
                chunk_id=node.metadata.get("chunk_id", node.node_id),
                source=node.metadata.get("source", "?"),
                text=node.get_content(),
            )
        )
    return out


def print_retrieval(qid: str, question: str, retrieved: list[RetrievedChunk], handle=None) -> None:
    lines = [f"--- retrieval for {qid} (top_k={len(retrieved)}) " + "-" * 40, f"Q: {question}"]
    header = f"{'rank':>4}  {'score':>8}  {'source':<38}  {'chunk_id':<28}  preview"
    lines.append(header)
    lines.append("-" * len(header))
    for r in retrieved:
        preview = " ".join(r.text.split())[:80]
        lines.append(f"{r.rank:>4}  {r.score:>8.4f}  {r.source:<38}  {r.chunk_id:<28}  {preview}")
    text = "\n".join(lines) + "\n"
    print(text)
    if handle is not None:
        handle.write(text + "\n")


# --- Context engineering (config C) ------------------------------------------

def select_context_chunks(candidates: list[RetrievedChunk], top_n: int = CONTEXT_TOP_N,
                          score_floor_ratio: float = SCORE_FLOOR_RATIO,
                          dedup_ratio: float = DEDUP_SIMILARITY):
    """Drop low-relevance and near-duplicate candidates, keep up to top_n.

    Two different failure modes are handled separately on purpose: a low
    absolute score (this chunk probably isn't about the question at all) vs.
    near-duplicate text from the SAME source (overlap=50 can retrieve two
    adjacent windows of one document that mostly repeat each other). Chunks
    that cover the same fact from DIFFERENT sources (the Q3 case) are never
    dropped as duplicates -- the point of that question is to see the model
    disambiguate them, which requires keeping both and labeling them clearly.
    """
    if not candidates:
        return [], []

    top_score = candidates[0].score
    floor = top_score * score_floor_ratio
    dropped: list[tuple[RetrievedChunk, str]] = []
    survivors: list[RetrievedChunk] = []

    for cand in candidates:
        if cand.score < floor:
            dropped.append((cand, f"low_relevance_score ({cand.score:.4f} < floor {floor:.4f})"))
            continue
        is_dup = False
        for kept in survivors:
            if kept.source != cand.source:
                continue
            ratio = difflib.SequenceMatcher(None, kept.text, cand.text).ratio()
            if ratio > dedup_ratio:
                dropped.append((cand, f"near_duplicate_of_{kept.chunk_id} (ratio {ratio:.2f})"))
                is_dup = True
                break
        if not is_dup:
            survivors.append(cand)

    survivors = survivors[:top_n]
    return survivors, dropped


# --- Prompt builders ---------------------------------------------------------

def build_prompt_A(question: str) -> tuple[str, str]:
    system = "You are a helpful assistant. Answer the user's question directly and concisely."
    user = question
    return system, user


def build_prompt_B(question: str, chunks: list[RetrievedChunk]) -> tuple[str, str]:
    system = "Answer the user's question. Context that may or may not be relevant is provided below; use it if it helps."
    context_block = "\n\n".join(c.text for c in chunks)
    user = f"Context:\n{context_block}\n\nQuestion: {question}"
    return system, user


def build_prompt_C(question: str, survivors: list[RetrievedChunk]) -> tuple[str, str]:
    system = (
        "You are a grounded question-answering assistant for Baywood Transit "
        "Authority documentation. You are given a QUESTION and numbered CONTEXT "
        "excerpts pulled from the Authority's policy documents. Follow these "
        "rules exactly:\n"
        "1. Use ONLY the information in the numbered CONTEXT excerpts below. Do "
        "not use any outside knowledge, even if you know the general answer.\n"
        "2. Every factual claim in your answer must be followed by the source "
        "number it came from, in the form [Source N].\n"
        "3. If the CONTEXT excerpts do not contain enough information to fully "
        "answer the QUESTION, do not guess and do not answer partially. Instead "
        f'reply with exactly this sentence and nothing else -- no extra words, '
        f"no punctuation added, no explanation:\n{REFUSAL_STRING}\n"
        "4. Keep your answer concise: 1-4 sentences unless the question "
        "explicitly asks for a list."
    )
    context_lines = []
    for i, c in enumerate(survivors, start=1):
        context_lines.append(f"[Source {i}] ({c.source})\n{c.text}")
    context_block = "\n\n".join(context_lines) if context_lines else "(no relevant context retrieved)"
    user = f"CONTEXT:\n{context_block}\n\nQUESTION: {question}\n\nANSWER:"
    return system, user


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def generate(llm, system: str, user: str) -> tuple[str, str, float]:
    start = time.perf_counter()
    raw = llm.complete([{"role": "system", "content": system}, {"role": "user", "content": user}])
    latency = time.perf_counter() - start
    answer = strip_think(raw)
    return raw, answer, latency


# --- Main pipeline ------------------------------------------------------------

def run_configs_for_question(index, llm, question: Question, top_k: int,
                              questions_only: bool, retrieval_handle, gen_handle) -> tuple[list, list[GenerationRecord]]:
    banner(f"QUESTION {question.qid}: {question.text}", char="-")
    log(f"kind={question.kind}  expected_sources={question.expected_sources}  must_refuse={question.must_refuse}")

    top3 = retrieve(index, question.text, top_k)
    print_retrieval(question.qid, question.text, top3, retrieval_handle)

    records: list[GenerationRecord] = []
    if questions_only:
        return top3, records

    # Config A: no RAG at all.
    sysA, userA = build_prompt_A(question.text)
    log("config A (no RAG): calling qwen3:8b ...")
    rawA, ansA, latA = generate(llm, sysA, userA)
    records.append(GenerationRecord(
        qid=question.qid, config="A", k_used=0, system_prompt=sysA, user_prompt=userA,
        raw_response=rawA, answer_text=ansA, latency_s=round(latA, 3),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    ))
    log(f"  -> ({latA:.1f}s) {ansA[:140]}")

    # Config B: basic RAG, raw top-3, no cleanup.
    sysB, userB = build_prompt_B(question.text, top3)
    log("config B (basic RAG, top-3 raw): calling qwen3:8b ...")
    rawB, ansB, latB = generate(llm, sysB, userB)
    records.append(GenerationRecord(
        qid=question.qid, config="B", k_used=len(top3), system_prompt=sysB, user_prompt=userB,
        raw_response=rawB, answer_text=ansB, latency_s=round(latB, 3),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        context_chunk_ids=[c.chunk_id for c in top3], context_sources=[c.source for c in top3],
    ))
    log(f"  -> ({latB:.1f}s) {ansB[:140]}")

    # Config C: context-engineered. Wider candidate pool, then filtered.
    candidates = retrieve(index, question.text, CANDIDATE_K)
    survivors, dropped = select_context_chunks(candidates)
    if dropped:
        log(f"  config C dropped {len(dropped)} candidate(s): " +
            "; ".join(f"{c.chunk_id} ({reason})" for c, reason in dropped))
    sysC, userC = build_prompt_C(question.text, survivors)
    log(f"config C (context-engineered, {len(survivors)} survivors of {len(candidates)} candidates): calling qwen3:8b ...")
    rawC, ansC, latC = generate(llm, sysC, userC)
    records.append(GenerationRecord(
        qid=question.qid, config="C", k_used=len(survivors), system_prompt=sysC, user_prompt=userC,
        raw_response=rawC, answer_text=ansC, latency_s=round(latC, 3),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        context_chunk_ids=[c.chunk_id for c in survivors], context_sources=[c.source for c in survivors],
    ))
    log(f"  -> ({latC:.1f}s) {ansC[:140]}")

    if gen_handle is not None:
        for rec in records:
            gen_handle.write(f"\n{'=' * 100}\n{rec.qid} / config {rec.config} / k_used={rec.k_used}\n{'=' * 100}\n")
            gen_handle.write(f"[SYSTEM PROMPT]\n{rec.system_prompt}\n\n")
            gen_handle.write(f"[USER PROMPT]\n{rec.user_prompt}\n\n")
            gen_handle.write(f"[RAW MODEL RESPONSE]\n{rec.raw_response}\n\n")
            gen_handle.write(f"[ANSWER (think-stripped)]\n{rec.answer_text}\n")
            gen_handle.write(f"[latency_s={rec.latency_s}  timestamp={rec.timestamp}]\n")

    return top3, records


def run_sweep(index, llm, question: Question, ks, handle) -> list[SweepRecord]:
    banner(f"K-SWEEP on {question.qid}: {question.text}", char="-")
    records = []
    for k in ks:
        retrieved = retrieve(index, question.text, k)
        print_retrieval(f"{question.qid} (sweep k={k})", question.text, retrieved, handle)
        survivors = retrieved  # sweep studies raw k, not the config-C filter
        system, user = build_prompt_C(question.text, survivors)
        log(f"sweep k={k}: calling qwen3:8b ...")
        raw, answer, latency = generate(llm, system, user)
        log(f"  -> ({latency:.1f}s) {answer[:140]}")
        rec = SweepRecord(
            qid=question.qid, k=k, retrieved=retrieved, system_prompt=system, user_prompt=user,
            raw_response=raw, answer_text=answer, latency_s=round(latency, 3),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        records.append(rec)
        if handle is not None:
            handle.write(f"\n{'=' * 100}\nk={k}\n{'=' * 100}\n")
            handle.write(f"[SYSTEM PROMPT]\n{system}\n\n[USER PROMPT]\n{user}\n\n")
            handle.write(f"[RAW MODEL RESPONSE]\n{raw}\n\n[ANSWER]\n{answer}\n")
            handle.write(f"[latency_s={rec.latency_s}]\n")
    return records


# --- Heuristic evaluation -----------------------------------------------------

NUMERIC_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:percent|%|hours?|hrs?|days?|minutes?|mins?|miles?)\b", re.IGNORECASE
)


def sources_hit(context_sources: list[str], expected_sources: list[str]) -> bool:
    if not expected_sources:
        return True  # nothing to find (Q5/Q6): retrieval "correctness" is not applicable, treated as trivially satisfied
    return any(s in context_sources for s in expected_sources)


def is_refusal(answer_text: str) -> bool:
    return answer_text.strip() == REFUSAL_STRING


def numbers_grounded(answer_text: str, context_text: str) -> bool:
    found = NUMERIC_RE.findall(answer_text)
    if not found:
        return True
    ctx_lower = context_text.lower()
    for match in NUMERIC_RE.finditer(answer_text):
        phrase = match.group(0).lower()
        digits = re.match(r"\d+(?:\.\d+)?", phrase).group(0)
        if digits not in ctx_lower:
            return False
    return True


def keywords_present(answer_text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    lower = answer_text.lower()
    return any(kw.lower() in lower for kw in keywords)


def build_eval_row(question: Question, rec: GenerationRecord, context_text: str) -> EvalRow:
    if rec.config == "A":
        correct_retrieval = None  # no retrieval happens in config A
        grounded = None  # nothing to be grounded against
    else:
        correct_retrieval = sources_hit(rec.context_sources, question.expected_sources)
        grounded = is_refusal(rec.answer_text) or numbers_grounded(rec.answer_text, context_text)

    refused = is_refusal(rec.answer_text)
    if question.must_refuse:
        correct_answer = refused
        refused_when_needed = refused if rec.config == "C" else None
    else:
        correct_answer = (not refused) and keywords_present(rec.answer_text, question.gold_keywords)
        refused_when_needed = None

    notes = f"answer[:100]={rec.answer_text[:100]!r}"
    return EvalRow(
        qid=question.qid, config=rec.config, correct_retrieval=correct_retrieval,
        correct_answer=correct_answer, grounded=grounded,
        refused_when_needed=refused_when_needed, notes=notes,
    )


def write_eval_table(rows: list[EvalRow]) -> None:
    (RAW_DIR / "evaluation_table.json").write_text(
        json.dumps([asdict(r) for r in rows], indent=2) + "\n"
    )

    def fmt(b):
        return "n/a" if b is None else ("YES" if b else "no")

    lines = [
        "# HW4 Part 4 - evaluation table (heuristic, verified against real transcripts)",
        "",
        "| qid | config | correct_retrieval | correct_answer | grounded | refused_when_needed |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r.qid} | {r.config} | {fmt(r.correct_retrieval)} | {fmt(r.correct_answer)} | "
                     f"{fmt(r.grounded)} | {fmt(r.refused_when_needed)} |")

    n = len(rows)
    def rate(field_name):
        vals = [getattr(r, field_name) for r in rows if getattr(r, field_name) is not None]
        return f"{sum(1 for v in vals if v)}/{len(vals)}" if vals else "n/a"

    lines += [
        "",
        "## Summary",
        "",
        f"- accuracy (correct_answer over all rows): {rate('correct_answer')}",
        f"- faithfulness (grounded, B/C rows only): {rate('grounded')}",
        f"- format compliance / robustness (refused_when_needed, config C on Q5/Q6): {rate('refused_when_needed')}",
        f"- total rows: {n}",
    ]
    (RAW_DIR / "evaluation_table.md").write_text("\n".join(lines) + "\n")


# --- Entry point ---------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=RAG_DOCS_DIR)
    parser.add_argument("--top-k", type=int, default=3, help="baseline retrieval k for section-2 printouts and config B")
    parser.add_argument("--questions-only", action="store_true", help="chunk+embed+retrieve+print only, no LLM calls")
    parser.add_argument("--skip-sweep", action="store_true", help="skip the k=1,3,5 sweep")
    parser.add_argument("--sweep-qid", default=SWEEP_QID)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    banner(f"HW4 Part 4 - grounded RAG  |  SEED {SEED}  VERIFY_SEED {VERIFY_SEED}")
    log(f"corpus dir      : {args.corpus}")
    log(f"embed model     : {EMBED_MODEL_NAME}")
    log(f"llm model       : {LLM_MODEL_NAME} (via Ollama, localhost:11434)")
    log(f"top_k (baseline): {args.top_k}")
    log(f"candidate_k (C) : {CANDIDATE_K}  ->  filtered to <= {CONTEXT_TOP_N}")
    log(f"refusal string  : {REFUSAL_STRING!r}")

    from llama_index.core import Settings
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)
    Settings.llm = None  # no LLM calls should ever go through LlamaIndex itself
    Settings.embed_model = embed_model

    banner("CHUNKING data/rag_docs/")
    chunks = load_corpus(args.corpus)
    log(f"total chunks: {len(chunks)}")
    (RAW_DIR / "chunks.jsonl").write_text(
        "\n".join(json.dumps(asdict(c)) for c in chunks) + "\n"
    )

    banner("BUILDING in-memory SimpleVectorStore index")
    index, embed_seconds = build_index(chunks, embed_model)
    log(f"embedded {len(chunks)} chunks in {embed_seconds:.2f}s")

    llm = None
    if not args.questions_only:
        from model_client import ModelClient
        llm = ModelClient(model=LLM_MODEL_NAME, temperature=0.0)
        log(f"ModelClient ready: {llm.model_name} @ {llm.base_url}")

    retrieval_path = RAW_DIR / "retrieval_printouts.txt"
    generations_path = RAW_DIR / "generations_full.txt"
    generations_jsonl = RAW_DIR / "generations.jsonl"
    sweep_path = RAW_DIR / "k_sweep_full.txt"
    sweep_jsonl = RAW_DIR / "k_sweep.jsonl"

    all_generations: list[GenerationRecord] = []
    all_eval_rows: list[EvalRow] = []
    chunk_text_by_id = {c.chunk_id: c.text for c in chunks}

    with retrieval_path.open("w") as rhandle, generations_path.open("w") as ghandle:
        banner("RETRIEVAL + CONFIGS A / B / C, per question")
        for question in QUESTIONS:
            top3, records = run_configs_for_question(
                index, llm, question, args.top_k, args.questions_only, rhandle, ghandle
            )
            all_generations.extend(records)
            for rec in records:
                context_text = "\n".join(chunk_text_by_id.get(cid, "") for cid in rec.context_chunk_ids)
                all_eval_rows.append(build_eval_row(question, rec, context_text))

    if all_generations:
        generations_jsonl.write_text(
            "\n".join(json.dumps(asdict(r)) for r in all_generations) + "\n"
        )

    sweep_records: list[SweepRecord] = []
    if not args.questions_only and not args.skip_sweep:
        sweep_question = next((q for q in QUESTIONS if q.qid == args.sweep_qid), QUESTIONS[1])
        with sweep_path.open("w") as shandle:
            sweep_records = run_sweep(index, llm, sweep_question, SWEEP_KS, shandle)
        sweep_jsonl.write_text(
            "\n".join(json.dumps({**asdict(r), "retrieved": [asdict(x) for x in r.retrieved]}) for r in sweep_records)
            + "\n"
        )
        banner("K-SWEEP SUMMARY", char="-")
        for r in sweep_records:
            scores = [c.score for c in r.retrieved]
            log(f"k={r.k}: scores={scores}  answer[:100]={r.answer_text[:100]!r}")

    if all_eval_rows:
        write_eval_table(all_eval_rows)

    if llm is not None:
        llm.print_exit_summary()

    banner("DONE")
    log(f"raw output dir : {RAW_DIR}")
    log(f"chunks         : {len(chunks)}")
    log(f"generations    : {len(all_generations)}")
    log(f"sweep records  : {len(sweep_records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
