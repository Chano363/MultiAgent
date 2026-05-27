"""Minimal call type definitions expected by Agent Lightning."""

from enum import Enum


class CallTypes(str, Enum):
    completion = "completion"
    embedding = "embedding"
    image_generation = "image_generation"
