"""OCR fallback for scanned PDFs via RapidOCR (bundled ONNX models, CPU, offline).

The engine is loaded lazily and cached: importing this module is cheap, and
documents with a real text layer never pay the model-load cost.
"""

import io
import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _engine() -> Any:
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def ocr_image_bytes(data: bytes) -> str:
    """Extract text from one image; returns "" when nothing is recognized."""
    import numpy as np
    from PIL import Image

    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        logger.warning("ocr: unreadable embedded image, skipping", exc_info=True)
        return ""
    result, _ = _engine()(np.asarray(image))
    if not result:
        return ""
    return "\n".join(str(line[1]) for line in result)
