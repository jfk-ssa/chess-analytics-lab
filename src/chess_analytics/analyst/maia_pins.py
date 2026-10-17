"""Pinned Maia-3 identities. This repository does not contain the weights or the code."""

CODE_REPO = "https://github.com/CSSLab/maia3"
CODE_COMMIT = "1e13597c42d4858b7cfd7cfdae01e297263364b2"
RATING_SCALE = "lichess-blitz"
ALIASES = ("5M", "23M", "79M")
DEFAULT_ALIAS = "23M"

# Published Hugging Face blobs checked on 2026-10-17. The fetch script refuses
# any other bytes. The checked tool still hashes the local file named in config.
PINS = {
    "5M": {
        "model_name": "maia3-5m",
        "filename": "maia3-5m.pt",
        "hf_repo": "UofTCSSLab/Maia3-5M",
        "hf_revision": "b6559de2398d7140b985f28fd2c19fb5e47ddabe",
        "sha256": "ba14208b2992d85502f5fb501934abf6aaaeb355e9f3fdf90e326911f562524f",
        "bytes": 20_968_049,
    },
    "23M": {
        "model_name": "maia3-23m",
        "filename": "maia3-23m.pt",
        "hf_repo": "UofTCSSLab/Maia3-23M",
        "hf_revision": "51a0145a8178046f7de23119160b136672deeb2b",
        "sha256": "bce6cd1af5f0399ac7eed33fabb7a6a2ef6193662c2740f262bf93af7bfb3569",
        "bytes": 91_799_307,
    },
    "79M": {
        "model_name": "maia3-79m",
        "filename": "maia3-79m.pt",
        "hf_repo": "UofTCSSLab/Maia3-79M",
        "hf_revision": "a107d6ceb7b298cb04ae1da4edffe2939858b894",
        "sha256": "3fc6181d5db789b45a15305732148757ae74efa3e0028e81ba335b462dac45c2",
        "bytes": 315_651_851,
    },
}
