"""Replaceable ModelAcquisitionProvider adapters."""

from kultrun.adapters.acquisition.fixture import FixtureAcquisitionProvider
from kultrun.adapters.acquisition.huggingface import HuggingFaceAcquisitionProvider

__all__ = ["FixtureAcquisitionProvider", "HuggingFaceAcquisitionProvider"]
