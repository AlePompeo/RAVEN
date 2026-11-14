# Third-party notices

Components that are downloaded by the optional installer step (`./install.sh --with-llm`, `scripts/install_local_llm.py`) and run as a
separate local process. They are not part of this repository's source and are not redistributed in it.

| Component | Version | Licence | Origin |
|---|---|---|---|
| llama.cpp (`llama-server` and its libraries) | build b12110 | MIT | ggml-org, https://github.com/ggml-org/llama.cpp |
| Ministral 3 3B Instruct 2512, Q4_K_M quantisation | 2512 | Apache-2.0 | Mistral AI; GGUF conversion by Unsloth, https://huggingface.co/unsloth/Ministral-3-3B-Instruct-2512-GGUF |

The licence texts travel with the downloaded files (llama.cpp archive: `LICENSE`; model repository: `LICENSE`). Files are checked against a
pinned size and SHA-256 before use (see `scripts/install_local_llm.py`).

Other alternatives that were measured and not shipped (Granite 4.0, Phi-4-mini, SmolLM3) are listed in `docs/process/BACKLOG.md`.
