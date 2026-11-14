# SPDX-License-Identifier: Apache-2.0
"""Inferenza ONNX per il predittore NN: solo numpy + onnxruntime (mai torch)."""

from typing import Any

import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped,import-not-found,unused-ignore]
from numpy.typing import NDArray


def make_session(blob: bytes) -> Any:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    return ort.InferenceSession(blob, sess_options=opts, providers=["CPUExecutionProvider"])


def onnx_predict(session: Any, x: NDArray[np.float64]) -> NDArray[np.float64]:
    name = session.get_inputs()[0].name
    out = session.run(None, {name: np.asarray(x, dtype=np.float32)})[0]
    return np.asarray(out, dtype=np.float64).ravel()
