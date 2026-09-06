"""Hugging Face identity adapter. Live Hub fetch is deferred (K-35)."""

from kultrun.adapters.model_source.huggingface import HuggingFaceSource, build

__all__ = ["HuggingFaceSource", "build"]
