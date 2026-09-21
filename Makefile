# DATA260 - convenience targets. Everything here is a one-line wrapper around a
# command already documented in README.md; nothing happens only via make.
#
# SID4 3170 -> PORT_BASE 8470, PREFIX s3170, DOMAIN_ID 2 (Municipal Transit Incidents)

PY      ?= .venv/bin/python
PORT    ?= 8470
APP_DIR := code/web_application

.PHONY: help install nltk run corpus corpus-verify warmup rag metrics verify-hw03 hw3 clean-hw3

help:
	@echo "install       install deps from requirements.txt, then the NLTK data"
	@echo "nltk          download just the NLTK sentence tokenizer"
	@echo "run           serve the authenticated app on port $(PORT)"
	@echo "corpus        download the transit corpus + write SOURCES.md and CORPUS_MANIFEST.json"
	@echo "corpus-verify re-hash data/corpus against the manifest (no network)"
	@echo "warmup        Tiny Shakespeare smoke test of the three chunkers"
	@echo "rag           run the three retrieval pipelines, tee-ing RUN_LOG.txt"
	@echo "metrics       recompute reports/hw03/METRICS.md from reports/hw03/raw/"
	@echo "verify-hw03   run the HW3 self-check -> reports/hw03/verification.json"
	@echo "hw3           corpus -> rag -> metrics -> verify-hw03"

install:
	$(PY) -m pip install -r requirements.txt
	$(MAKE) nltk

# The semantic and sentence-window chunkers split on sentences using NLTK's
# punkt tokenizer. LlamaIndex fetches it lazily, part-way through the run;
# fetching it here means a network problem shows up now instead of several
# minutes into `make rag`, after the token stage has already been paid for.
nltk:
	$(PY) -m nltk.downloader punkt_tab stopwords

run:
	cd $(APP_DIR) && ../../$(PY) -m uvicorn app:app --reload --port $(PORT)

corpus:
	$(PY) code/fetch_corpus.py

corpus-verify:
	$(PY) code/fetch_corpus.py --verify

warmup:
	$(PY) code/run_rag_chunking.py --warmup

# caffeinate keeps the Mac awake: semantic chunking embeds every sentence in the
# corpus and is the slow one.
#
# python -u matters here. Piping to tee makes Python block-buffer stdout, so
# without it RUN_LOG.txt sits empty for the whole run and there is no way to
# tell progress from a hang. -u forces unbuffered output so the log streams.
rag: nltk
	caffeinate -i $(PY) -u code/run_rag_chunking.py 2>&1 | tee reports/hw03/RUN_LOG.txt

metrics:
	$(PY) code/summarize_rag_metrics.py

verify-hw03:
	$(PY) code/verify_hw03.py

hw3: corpus rag metrics verify-hw03

clean-hw3:
	rm -f reports/hw03/raw/retrieval_rows.* reports/hw03/raw/chunk_stats.json \
	      reports/hw03/raw/query_vectors.json reports/hw03/METRICS.md
