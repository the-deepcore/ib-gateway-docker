from __future__ import annotations

from typing import Dict, List

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.clock.clock_services import build_from_index, slice_clock

from .splitter_data import SplitConfig


def _fixed(clock: Clock, cfg: SplitConfig) -> List[Dict[str, Clock]]:
    if not (cfg.train_start and cfg.train_end and cfg.test_start and cfg.test_end):
        raise ValueError("fixed split needs train_start/train_end/test_start/test_end")
    tr = slice_clock(clock, cfg.train_start, cfg.train_end)
    te = slice_clock(clock, cfg.test_start, cfg.test_end)
    return [{"train": tr, "test": te}]


def _walk_bars(clock: Clock, cfg: SplitConfig) -> List[Dict[str, Clock]]:
    tb = int(cfg.train_bars or 0)
    vb = int(cfg.test_bars or 0)
    sb = int(cfg.stride_bars or 0)
    gb = int(cfg.gap_bars or 0)
    if tb <= 0 or vb <= 0 or sb <= 0:
        raise ValueError("walk_bars needs positive train_bars, test_bars, stride_bars")

    idx = clock.index
    n = len(idx)
    out: List[Dict[str, Clock]] = []

    i = 0
    while True:
        tr_start = i
        tr_end = tr_start + tb - 1
        gap_start = tr_end + 1
        te_start = gap_start + gb
        te_end = te_start + vb - 1
        if te_end >= n:
            if cfg.include_tail and te_start < n:
                tr_clock = build_from_index(idx[tr_start:tr_end + 1])
                te_clock = build_from_index(idx[te_start:n])
                out.append({"train": tr_clock, "test": te_clock})
            break

        tr_clock = build_from_index(idx[tr_start:tr_end + 1])
        te_clock = build_from_index(idx[te_start:te_end + 1])
        out.append({"train": tr_clock, "test": te_clock})

        i += sb
        if i + tb + gb + vb - 1 >= n:
            if cfg.include_tail and (i + tb + gb) < n:
                tr_clock = build_from_index(idx[i : min(i + tb, n)])
                te_clock = build_from_index(idx[i + tb + gb : n])
                out.append({"train": tr_clock, "test": te_clock})
            break


    return out


def build_splits(clock: Clock, cfg: SplitConfig) -> List[Dict[str, Clock]]:
    m = cfg.mode
    if m == "fixed":
        return _fixed(clock, cfg)
    if m == "walk_bars":
        return _walk_bars(clock, cfg)
    raise ValueError("unsupported split mode")
