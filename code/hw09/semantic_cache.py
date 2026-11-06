"""
HW9 Part 2/3 - semantic response cache at the ingress of the Q&A endpoint.

Redis Stack (RediSearch) holds one HASH per cached answer under  s3170:<ns>:<n>  with
   query, answer, embedding (FLOAT32 x 384, normalised), data_version, entities, created_at
and a vector index over `embedding` (HNSW, COSINE). Lookup is a KNN-1 query; similarity = 1 - cosine distance.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Callable

import common  # noqa: F401
import numpy as np
import redis
from qa_agent import data_version, extract_entities, run_agent
from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

PREFIX = common.PREFIX
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"      # same MiniLM HW3 used; 384-d
DIM = 384
DEFAULT_THRESHOLD = 0.85

log = logging.getLogger("s3170.semcache")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)

_model = None


def embed(text_: str) -> np.ndarray:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBED_MODEL)
    return np.asarray(_model.encode(text_, normalize_embeddings=True), dtype=np.float32)


class SemanticCache:
    def __init__(self, namespace: str = "sem", threshold: float = DEFAULT_THRESHOLD, client=None):
        self.ns = namespace
        self.key_prefix = f"{PREFIX}:{namespace}:"
        self.index = f"{PREFIX}_{namespace}_idx"
        self.threshold = threshold
        self.r = client or redis.Redis.from_url(REDIS_URL, decode_responses=False)   # vectors are binary
        self.ft = self.r.ft(self.index)

    # --- index ------------------------------------------------------------------------------
    def create_index(self, reset: bool = False) -> None:
        if reset:
            self.reset()
        try:
            self.ft.info()
            return
        except redis.ResponseError:
            pass
        self.ft.create_index(
            [TextField("query"), TextField("answer"), TagField("entities"),
             VectorField("embedding", "HNSW", {"TYPE": "FLOAT32", "DIM": DIM, "DISTANCE_METRIC": "COSINE"})],
            definition=IndexDefinition(prefix=[self.key_prefix], index_type=IndexType.HASH))

    def reset(self) -> None:
        try:
            self.ft.dropindex(delete_documents=True)
        except redis.ResponseError:
            pass
        for k in self.r.scan_iter(match=f"{self.key_prefix}*"):
            self.r.delete(k)

    def size(self) -> int:
        return sum(1 for _ in self.r.scan_iter(match=f"{self.key_prefix}*"))

    # --- store / lookup / invalidate -------------------------------------------------------------
    def store(self, query: str, answer: str, version: str, entities: list[str], vec: np.ndarray | None = None) -> str:
        key = f"{self.key_prefix}{uuid.uuid4().hex[:12]}"
        vec = embed(query) if vec is None else vec
        self.r.hset(key, mapping={"query": query, "answer": answer, "data_version": version,
                                  "entities": ",".join(entities) or "none", "created_at": time.time(),
                                  "embedding": vec.tobytes()})
        return key

    def nearest(self, vec: np.ndarray) -> dict[str, Any] | None:
        q = (Query("*=>[KNN 1 @embedding $v AS dist]").return_fields("query", "answer", "data_version", "entities", "dist")
             .sort_by("dist").dialect(2))
        res = self.ft.search(q, query_params={"v": vec.tobytes()})
        if not res.docs:
            return None
        d = res.docs[0]
        dec = lambda x: x.decode() if isinstance(x, bytes) else x   # noqa: E731
        return {"key": dec(d.id), "query": dec(d.query), "answer": dec(d.answer), "data_version": dec(d.data_version),
                "entities": dec(d.entities), "similarity": round(1.0 - float(dec(d.dist)), 4)}

    def lookup(self, query: str, threshold: float | None = None) -> dict[str, Any]:
        """One timed similarity search. Returns the nearest neighbour and whether it clears the threshold."""
        th = self.threshold if threshold is None else threshold
        t0 = time.perf_counter()
        vec = embed(query)
        t1 = time.perf_counter()
        near = self.nearest(vec)
        t2 = time.perf_counter()
        return {"vec": vec, "neighbour": near, "hit": bool(near and near["similarity"] >= th), "threshold": th,
                "embed_ms": (t1 - t0) * 1000, "search_ms": (t2 - t1) * 1000}

    def invalidate(self, key: str) -> None:
        self.r.delete(key)

    # --- the query handler ------------------------------------------------------------------------
    def handle(self, query: str, threshold: float | None = None, validate_version: bool = True,
               agent: Callable[[str], dict[str, Any]] = run_agent) -> dict[str, Any]:
        """Ingress handler. hit -> stored answer, agent NOT run. miss -> HW8 agent path, then store."""
        t_start = time.perf_counter()
        look = self.lookup(query, threshold)
        near = look["neighbour"]
        stale_evicted = None
        if look["hit"] and validate_version:
            t_v = time.perf_counter()
            current = data_version(extract_entities(near["query"]))
            version_ms = (time.perf_counter() - t_v) * 1000
            if current != near["data_version"]:
                log.info("STALE  similarity=%.4f stored_version=%s current_version=%s -> evicting, treating as a miss",
                         near["similarity"], near["data_version"], current)
                self.invalidate(near["key"])
                stale_evicted = {"stored": near["data_version"], "current": current, "evicted_query": near["query"]}
                look["hit"] = False
            else:
                look["version_check_ms"] = version_ms
        if look["hit"]:
            total_ms = (time.perf_counter() - t_start) * 1000
            log.info("CACHE HIT  similarity=%.4f threshold=%.2f matched=%r latency=%.1f ms",
                     near["similarity"], look["threshold"], near["query"], total_ms)
            return {"query": query, "answer": near["answer"], "is_cached": True, "similarity": near["similarity"],
                    "matched_query": near["query"], "threshold": look["threshold"], "latency_ms": round(total_ms, 2),
                    "embed_ms": round(look["embed_ms"], 2), "search_ms": round(look["search_ms"], 2),
                    "version_check_ms": round(look.get("version_check_ms", 0.0), 2), "stale_evicted": None}
        sim = near["similarity"] if near else None
        log.info("CACHE MISS  nearest_similarity=%s threshold=%.2f -> running the HW8 agent path",
                 f"{sim:.4f}" if sim is not None else "n/a", look["threshold"])
        t_a = time.perf_counter()
        out = agent(query)
        agent_ms = (time.perf_counter() - t_a) * 1000
        self.store(query, out["answer"], out["data_version"], out["entities"], vec=look["vec"])
        total_ms = (time.perf_counter() - t_start) * 1000
        log.info("CACHE MISS  agent_ms=%.0f total=%.0f ms stored version=%s", agent_ms, total_ms, out["data_version"])
        return {"query": query, "answer": out["answer"], "is_cached": False, "similarity": sim,
                "matched_query": near["query"] if near else None, "threshold": look["threshold"],
                "latency_ms": round(total_ms, 2), "embed_ms": round(look["embed_ms"], 2),
                "search_ms": round(look["search_ms"], 2), "agent_ms": round(agent_ms, 2),
                "data_version": out["data_version"], "stale_evicted": stale_evicted}
