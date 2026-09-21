#!/usr/bin/env python3
"""
HW3 Part 2 - retrieval-only RAG: compare three LlamaIndex chunking techniques.

Builds one in-memory vector index per chunking technique over the Municipal
Transit Incidents corpus (DOMAIN_ID 2), runs every question in
reports/hw03/questions.yaml against all three, and writes the per-query,
per-technique retrieval output to reports/hw03/raw/ as machine-readable data.

No LLM is involved anywhere in this file. Nothing is generated; the only model
used is the sentence embedding model, and the only operation is nearest-
neighbour search over chunk embeddings. That is what "retrieval-only" means
here, and it is why the results are deterministic: re-running this script on the
same corpus reproduces the same scores exactly.

Techniques
    token     TokenTextSplitter              fixed token budget + overlap
    semantic  SemanticSplitterNodeParser     breaks where adjacent sentences
                                             stop being similar to each other
    sentence  SentenceWindowNodeParser       one sentence per node, with the
                                             neighbouring sentences carried in
                                             metadata (embedded on the sentence
                                             alone, so retrieval is precise but
                                             the surrounding context survives)

Outputs (all under reports/hw03/raw/)
    retrieval_rows.jsonl   one row per (question, technique, rank)
    retrieval_rows.csv     the same rows, flat
    chunk_stats.json       per-technique corpus-level chunking statistics
    query_vectors.json     query embedding dimension and first 8 values

Usage
    python run_rag_chunking.py                 # graded run over the five questions
    python run_rag_chunking.py --include-extra # also run the optional extras
    python run_rag_chunking.py --warmup        # Tiny Shakespeare smoke test only
    python run_rag_chunking.py --top-k 5
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import textwrap
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
REPORT_DIR = REPO_ROOT / "reports" / "hw03"
RAW_DIR = REPORT_DIR / "raw"
QUESTIONS_PATH = REPORT_DIR / "questions.yaml"

PREVIEW_CHARS = 160
SEED = 3170          # SID4; recorded in the output for traceability
VERIFY_SEED = 263170  # 260000 + SID4

TINY_SHAKESPEARE_URL = (
    "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/"
    "tinyshakespeare/input.txt"
)


# --- Data model ----------------------------------------------------------

@dataclass
class RetrievalRow:
    """One retrieved chunk, for one question, under one chunking technique."""

    question_id: str
    question: str
    technique: str
    rank: int
    store_score: float          # similarity the retriever itself reported
    cosine_sim: float           # recomputed explicitly from the two embeddings
    chunk_len_chars: int
    chunk_len_tokens_est: int
    embedded_text_len_chars: int   # what was actually embedded (see below)
    window_len_chars: int       # sentence-window only; equals chunk_len otherwise
    source_file: str
    expected_source_file: str
    is_expected_source: bool
    node_id: str
    preview: str
    retrieval_latency_ms: float  # per-query, repeated on each of its rows
    embed_dim: int


@dataclass
class TechniqueStats:
    technique: str
    parser: str
    parser_config: dict
    n_chunks: int
    avg_chunk_len_chars: float
    avg_chunk_len_tokens_est: float
    min_chunk_len_chars: int
    max_chunk_len_chars: int
    build_seconds: float
    embed_seconds: float
    per_file_chunk_counts: dict = field(default_factory=dict)


# --- Helpers -------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Cheap token estimate. Whitespace words scaled by the usual ~1.3 ratio.

    A real tokenizer would be better, but the chunkers are configured in
    different units anyway (tokens for TokenTextSplitter, sentences for the
    other two), so this column exists only to make the three comparable at a
    glance. It is labelled 'est' everywhere so nobody reads it as exact.
    """
    return int(len(text.split()) * 1.3)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if denominator == 0.0 else float(np.dot(a, b) / denominator)


def preview_of(text: str) -> str:
    flat = " ".join(text.split())
    return flat[:PREVIEW_CHARS]


def banner(title: str, char: str = "=") -> None:
    print()
    print(char * 100)
    print(title)
    print(char * 100)


def ensure_sentence_tokenizer() -> None:
    """Make sure NLTK's sentence tokenizer is on disk before the run starts.

    SemanticSplitterNodeParser and SentenceWindowNodeParser both split on
    sentences using NLTK's punkt tokenizer, which LlamaIndex downloads lazily
    on first use. Lazily means *after* the token-chunking stage has already
    run, so on a machine that cannot reach the NLTK data host the job dies
    several minutes in, having thrown away that work. Pulling the download to
    the front makes that failure immediate and legible.
    """
    import nltk

    needed = (("punkt_tab", "tokenizers/punkt_tab"), ("stopwords", "corpora/stopwords"))
    for resource, probe in needed:
        try:
            nltk.data.find(probe)
            continue
        except LookupError:
            pass

        print(f"downloading NLTK '{resource}' (one-time, a few MB)...")
        if not nltk.download(resource, quiet=True):
            sys.exit(
                f"\nCould not download the NLTK '{resource}' resource, which the\n"
                "semantic and sentence-window chunkers both need.\n\n"
                "Fix it with either of:\n"
                f"    python -m nltk.downloader {resource}\n"
                "    make nltk\n"
            )
        try:
            nltk.data.find(probe)
        except LookupError:
            sys.exit(f"NLTK reported '{resource}' downloaded but it is still not findable.")


# --- Index construction --------------------------------------------------

def build_parsers(embed_model):
    """The three chunkers, with the configuration choices spelled out.

    Token chunk_size 512 with 64 overlap: 512 tokens is roughly a long
    paragraph of regulatory prose, and MiniLM truncates at 256 word-pieces, so
    anything much larger would be partly invisible to the embedding anyway. The
    64-token overlap (12.5%) is there so a sentence that straddles a boundary
    still appears whole in one of the two neighbouring chunks.

    Semantic buffer_size 2: the splitter compares each sentence group against
    the next; a buffer of 2 smooths over the one-sentence asides that federal
    prose is full of ("See paragraph (b) of this section.") which would
    otherwise trigger a spurious break. breakpoint_percentile 95 keeps breaks
    rare, so chunks stay topical rather than fragmenting.

    Sentence-window window_size 3: three sentences either side. That is enough
    to carry a probable-cause statement together with the finding it follows,
    without pulling in a whole page.
    """
    from llama_index.core.node_parser import (
        SemanticSplitterNodeParser,
        SentenceWindowNodeParser,
        TokenTextSplitter,
    )

    token_parser = TokenTextSplitter(chunk_size=512, chunk_overlap=64, separator=" ")

    semantic_parser = SemanticSplitterNodeParser(
        buffer_size=2,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model,
    )

    sentence_parser = SentenceWindowNodeParser.from_defaults(
        window_size=3,
        window_metadata_key="window",
        original_text_metadata_key="original_sentence",
    )

    return [
        ("token", "TokenTextSplitter", token_parser,
         {"chunk_size": 512, "chunk_overlap": 64}),
        ("semantic", "SemanticSplitterNodeParser", semantic_parser,
         {"buffer_size": 2, "breakpoint_percentile_threshold": 95}),
        ("sentence", "SentenceWindowNodeParser", sentence_parser,
         {"window_size": 3}),
    ]


def load_corpus(directory: Path):
    from llama_index.core import SimpleDirectoryReader

    if not directory.exists() or not any(directory.iterdir()):
        sys.exit(
            f"Corpus directory {directory} is empty.\n"
            "Run:  python code/fetch_corpus.py\n"
            "(that script needs unrestricted network access -- run it in a normal shell)"
        )

    documents = SimpleDirectoryReader(
        input_dir=str(directory),
        filename_as_id=True,
        required_exts=[".txt", ".pdf", ".md"],
    ).load_data()

    total_chars = sum(len(d.text) for d in documents)
    print(f"Loaded {len(documents)} document parts from {directory}")
    print(f"  total extracted text: {total_chars:,} characters")
    by_file: dict[str, int] = {}
    for document in documents:
        name = document.metadata.get("file_name", "?")
        by_file[name] = by_file.get(name, 0) + len(document.text)
    for name, size in sorted(by_file.items()):
        print(f"    {name:<58} {size:>9,} chars")
    return documents


def build_index(technique, parser, documents, embed_model):
    """Chunk, embed and index. Returns (index, nodes, build_s, embed_s)."""
    from llama_index.core import VectorStoreIndex

    start = time.perf_counter()
    nodes = parser.get_nodes_from_documents(documents, show_progress=False)
    build_seconds = time.perf_counter() - start

    start = time.perf_counter()
    # No vector_store argument -> SimpleVectorStore, which is the in-memory
    # store the assignment asks for. Nothing is written to disk.
    index = VectorStoreIndex(nodes, embed_model=embed_model, show_progress=False)
    embed_seconds = time.perf_counter() - start

    return index, nodes, build_seconds, embed_seconds


def summarise_nodes(technique, parser_name, parser_config, nodes,
                    build_seconds, embed_seconds) -> TechniqueStats:
    lengths = [len(n.get_content()) for n in nodes]
    token_estimates = [estimate_tokens(n.get_content()) for n in nodes]

    per_file: dict[str, int] = {}
    for node in nodes:
        name = node.metadata.get("file_name", "?")
        per_file[name] = per_file.get(name, 0) + 1

    return TechniqueStats(
        technique=technique,
        parser=parser_name,
        parser_config=parser_config,
        n_chunks=len(nodes),
        avg_chunk_len_chars=round(sum(lengths) / len(lengths), 1) if lengths else 0.0,
        avg_chunk_len_tokens_est=round(sum(token_estimates) / len(token_estimates), 1)
                                 if token_estimates else 0.0,
        min_chunk_len_chars=min(lengths) if lengths else 0,
        max_chunk_len_chars=max(lengths) if lengths else 0,
        build_seconds=round(build_seconds, 2),
        embed_seconds=round(embed_seconds, 2),
        per_file_chunk_counts=dict(sorted(per_file.items())),
    )


# --- The retrieval-only function the assignment asks for -----------------

def retrieve_and_report(index, embed_model, technique, question_id, question,
                        expected_source, top_k) -> tuple[list[RetrievalRow], list[float]]:
    """Retrieve top-k for one query and print everything the spec requires.

    Prints the query embedding dimension and its first 8 values, then a table of
    rank / store_score / cosine_sim / chunk_len / preview, then the shapes of the
    query vector and the stacked document vectors.

    The cosine column is NOT copied from the store score: the retrieved chunks
    are re-embedded here and the cosine is computed explicitly against the query
    embedding. For this setup the two agree closely, which is the point -- it
    confirms the store score really is cosine similarity and not some other
    metric.

    The re-embedding uses MetadataMode.EMBED, not the bare node text. That
    matters: LlamaIndex embeds a node together with whatever metadata is not on
    its exclusion list, so for SentenceWindowNodeParser the indexed string is
    the sentence plus file metadata, while node.get_content() alone returns just
    the sentence. Embedding the bare text produced cosines that disagreed with
    the store score by as much as 0.18 -- not a scoring bug, just a different
    string. chunk_len_chars still measures the bare chunk, because that is what
    "chunk length" means in the comparison table.
    """
    from llama_index.core.schema import MetadataMode
    query_vector = np.asarray(embed_model.get_query_embedding(question), dtype=np.float32)

    retriever = index.as_retriever(similarity_top_k=top_k)
    start = time.perf_counter()
    results = retriever.retrieve(question)
    latency_ms = (time.perf_counter() - start) * 1000.0

    print()
    print(f"--- technique: {technique}  |  question: {question_id} " + "-" * 30)
    print(textwrap.fill(f"Q: {question}", width=100, subsequent_indent="   "))
    print(f"query embedding dim : {query_vector.shape[0]}")
    print(f"query first 8 values: "
          f"[{', '.join(f'{v: .6f}' for v in query_vector[:8])}]")
    print(f"expected source     : {expected_source}")
    print()

    document_vectors = []
    rows: list[RetrievalRow] = []

    header = (f"{'rank':>4}  {'store_score':>11}  {'cosine_sim':>10}  {'chunk_len':>9}  "
              f"{'hit':>3}  {'source_file':<44}  preview")
    print(header)
    print("-" * len(header))

    for rank, scored_node in enumerate(results, start=1):
        node = scored_node.node
        text = node.get_content(metadata_mode=MetadataMode.NONE)
        embedded_text = node.get_content(metadata_mode=MetadataMode.EMBED)

        document_vector = np.asarray(
            embed_model.get_text_embedding(embedded_text), dtype=np.float32
        )
        document_vectors.append(document_vector)

        source_file = node.metadata.get("file_name", "?")
        is_hit = source_file == expected_source
        window_text = node.metadata.get("window", text)
        cosine_sim = cosine(query_vector, document_vector)

        rows.append(
            RetrievalRow(
                question_id=question_id,
                question=question,
                technique=technique,
                rank=rank,
                store_score=round(float(scored_node.score or 0.0), 6),
                cosine_sim=round(cosine_sim, 6),
                chunk_len_chars=len(text),
                chunk_len_tokens_est=estimate_tokens(text),
                embedded_text_len_chars=len(embedded_text),
                window_len_chars=len(window_text),
                source_file=source_file,
                expected_source_file=expected_source,
                is_expected_source=is_hit,
                node_id=node.node_id,
                preview=preview_of(text),
                retrieval_latency_ms=round(latency_ms, 3),
                embed_dim=int(query_vector.shape[0]),
            )
        )

        print(f"{rank:>4}  {float(scored_node.score or 0.0):>11.6f}  {cosine_sim:>10.6f}  "
              f"{len(text):>9}  {'YES' if is_hit else ' no':>3}  {source_file[:44]:<44}  "
              f"{preview_of(text)[:70]}")

    stacked = np.vstack(document_vectors) if document_vectors else np.empty((0, 0))
    print()
    if len(results) < top_k:
        print(f"note: retriever returned {len(results)} of {top_k} requested "
              f"(the store drops exact-duplicate chunk embeddings)")
    print(f"query vector shape        : {tuple(query_vector.shape)}")
    print(f"stacked doc vectors shape : {tuple(stacked.shape)}")
    print(f"retrieval latency         : {latency_ms:.3f} ms")

    return rows, [float(v) for v in query_vector[:8]]


# --- Warm-up -------------------------------------------------------------

def run_warmup(embed_model, top_k: int) -> None:
    """Tiny Shakespeare smoke test, exactly as the handout suggests.

    Its only job is to prove the three parsers and the in-memory index work
    before spending minutes embedding the real corpus. Nothing from this run is
    reported; the graded dataset is data/corpus/.
    """
    from llama_index.core import Document

    banner("WARM-UP: Tiny Shakespeare (not the graded dataset)")
    cache = RAW_DIR / "tinyshakespeare_input.txt"
    if not cache.exists():
        print(f"downloading {TINY_SHAKESPEARE_URL}")
        cache.write_bytes(urllib.request.urlopen(TINY_SHAKESPEARE_URL, timeout=60).read())
    text = cache.read_text(encoding="utf-8")[:120_000]
    print(f"using first {len(text):,} characters")

    documents = [Document(text=text, metadata={"file_name": "tinyshakespeare_input.txt"})]

    for technique, parser_name, parser, _config in build_parsers(embed_model):
        index, nodes, build_s, embed_s = build_index(technique, parser, documents, embed_model)
        print(f"\n{technique:<9} {parser_name:<30} {len(nodes):>5} chunks  "
              f"(chunk {build_s:.1f}s, embed {embed_s:.1f}s)")
        retrieve_and_report(
            index, embed_model, technique, "warmup",
            "Who plots against Caesar and why?",
            "tinyshakespeare_input.txt", top_k,
        )


# --- Main ----------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=None,
                        help="override top_k from questions.yaml")
    parser.add_argument("--include-extra", action="store_true",
                        help="also run the optional extra questions")
    parser.add_argument("--warmup", action="store_true",
                        help="run the Tiny Shakespeare smoke test and exit")
    parser.add_argument("--corpus", type=Path, default=CORPUS_DIR)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Keep tokenizer threads quiet and deterministic-ish in the log.
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    from llama_index.core import Settings

    # Importing llama_index.core first registers its bundled NLTK cache on
    # nltk.data.path, so this check sees a resource LlamaIndex already has.
    ensure_sentence_tokenizer()

    spec = yaml.safe_load(QUESTIONS_PATH.read_text())
    top_k = args.top_k or int(spec.get("top_k", 5))
    model_name = spec.get("embed_model", "sentence-transformers/all-MiniLM-L6-v2")

    banner(f"HW3 Part 2 - retrieval-only RAG  |  SEED {SEED}  VERIFY_SEED {VERIFY_SEED}")
    print(f"embedding model : {model_name}")
    print(f"top_k           : {top_k}")
    print(f"corpus          : {args.corpus}")
    print(f"questions       : {QUESTIONS_PATH}")

    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    embed_model = HuggingFaceEmbedding(model_name=model_name)

    # No LLM anywhere in this pipeline. Setting it to None makes LlamaIndex
    # raise instead of silently reaching for an OpenAI key if any code path
    # ever tried to synthesise an answer.
    Settings.llm = None
    Settings.embed_model = embed_model

    if args.warmup:
        run_warmup(embed_model, top_k)
        return 0

    documents = load_corpus(args.corpus)

    questions = list(spec["questions"])
    if args.include_extra:
        questions += list(spec.get("extra_questions", []))

    all_rows: list[RetrievalRow] = []
    all_stats: list[TechniqueStats] = []
    query_vector_log: dict[str, dict] = {}

    for technique, parser_name, node_parser, config in build_parsers(embed_model):
        banner(f"TECHNIQUE: {technique}  ({parser_name})")
        index, nodes, build_s, embed_s = build_index(
            technique, node_parser, documents, embed_model
        )
        stats = summarise_nodes(technique, parser_name, config, nodes, build_s, embed_s)
        all_stats.append(stats)

        print(f"chunks produced     : {stats.n_chunks}")
        print(f"avg chunk length    : {stats.avg_chunk_len_chars} chars "
              f"(~{stats.avg_chunk_len_tokens_est} tokens est.)")
        print(f"min / max chunk len : {stats.min_chunk_len_chars} / {stats.max_chunk_len_chars} chars")
        print(f"chunking time       : {stats.build_seconds}s")
        print(f"embedding time      : {stats.embed_seconds}s")
        print("chunks per file:")
        for name, count in stats.per_file_chunk_counts.items():
            print(f"    {name:<58} {count:>6}")

        for question in questions:
            rows, first8 = retrieve_and_report(
                index, embed_model, technique,
                question["id"], " ".join(question["question"].split()),
                question["expected_source_file"], top_k,
            )
            all_rows.extend(rows)
            query_vector_log.setdefault(question["id"], {
                "question": " ".join(question["question"].split()),
                "embed_dim": rows[0].embed_dim if rows else None,
                "first_8_values": first8,
            })

    write_raw_outputs(all_rows, all_stats, query_vector_log, top_k, model_name)

    banner("DONE")
    print(f"rows written    : {len(all_rows)}")
    print(f"raw output dir  : {RAW_DIR}")
    print("next            : python code/summarize_rag_metrics.py")
    return 0


def write_raw_outputs(rows, stats, query_vector_log, top_k, model_name) -> None:
    jsonl_path = RAW_DIR / "retrieval_rows.jsonl"
    with jsonl_path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(asdict(row)) + "\n")

    csv_path = RAW_DIR / "retrieval_rows.csv"
    if rows:
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))

    (RAW_DIR / "chunk_stats.json").write_text(
        json.dumps(
            {
                "seed": SEED,
                "verify_seed": VERIFY_SEED,
                "embed_model": model_name,
                "top_k": top_k,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "techniques": [asdict(s) for s in stats],
            },
            indent=2,
        )
        + "\n"
    )

    (RAW_DIR / "query_vectors.json").write_text(
        json.dumps(query_vector_log, indent=2) + "\n"
    )


if __name__ == "__main__":
    sys.exit(main())
