"""Daily event-driven backtester.

Look-ahead prevention (documented in docs/backtesting.md):
1. Signals for session t are computed from bars with date <= t only (`evaluate` asserts this).
2. Orders are placed after t's close and can only fill from session t+1 (entry window rules in
   `recommendations.outcomes.simulate`, identical to the live track record).
3. The tradable universe on day t is chosen by trailing 20-session traded value measured on data <= t
   (no use of today's index membership → reduces survivorship bias; delisted stocks remain in the data
   for the sessions they traded).
4. Cross-sectional relative strength, sector strength and market regime are recomputed from data <= t.
5. Whether a position is still open on day t is decided by its simulated exit date <= t (observable on t).
6. Fundamentals, news and F&O are excluded by default (their point-in-time history is incomplete);
   excluded components are reported, and the score is normalised over available components.

Known limitation: prices are back-adjusted for splits/bonuses using factors known today; this rescales
pre-event prices (ratios/indicators unchanged) and can marginally affect absolute-price filters.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from app.analytics.config import DEFAULTS
from app.analytics.evaluate import ExternalInputs, evaluate
from app.analytics.regime import RegimeInputs, compute_regime
from app.analytics.sector import BENCHMARK, rank_sectors, rs_percentiles, stock_relative_strength
from app.recommendations.outcomes import TradePlan, simulate
from app.technical.indicators import atr, ema, rsi

STRATEGIES = ("combined", "ranking", "breakout", "momentum", "mean_reversion")


@dataclass
class BacktestParams:
    strategy: str = "combined"
    start: date | None = None
    end: date | None = None
    capital: float = 1_000_000.0
    risk_pct: float = 1.0
    max_positions: int = 8
    max_position_pct: float = 20.0
    top_n: int = 5  # new entries considered per day
    slippage_bps: float = 10.0
    max_volume_participation: float = 0.02  # ≤2% of 20-day average volume
    universe_size: int = 250
    min_price: float = 20.0
    min_turnover_cr: float = 5.0
    min_score: float = 55.0
    split: tuple[float, float, float] = (0.6, 0.2, 0.2)
    weights: dict = field(default_factory=lambda: dict(DEFAULTS["scoring_weights"]))
    risk_cfg: dict = field(default_factory=lambda: dict(DEFAULTS["risk_limits"]))
    excl_cfg: dict = field(default_factory=lambda: dict(DEFAULTS["exclusions"]))
    regime_aware: bool = True


@dataclass
class BTTrade:
    symbol: str
    split: str
    signal_date: date
    entry_date: date
    entry_price: float
    exit_date: date | None
    exit_price: float | None
    quantity: int
    gross_pnl: float
    charges: float
    net_pnl: float
    exit_reason: str | None
    holding_sessions: int | None
    score: float | None


def _split_label(d: date, bounds: list[date]) -> str:
    return "train" if d <= bounds[0] else "validation" if d <= bounds[1] else "test"


def _mr_plan(df: pd.DataFrame) -> TradePlan | None:
    c = float(df["close"].iloc[-1])
    a = float(atr(df).iloc[-1])
    e20 = float(ema(df["close"], 20).iloc[-1])
    if not np.isfinite(a) or a <= 0:
        return None
    stop = c - 2.0 * a
    t1 = max(e20, c + 1.0 * a)
    return TradePlan(entry_low=c * 0.98, entry_high=c * 1.003, stop=stop, target1=t1, target2=c + 3.0 * a,
                     target3=None, trailing_after_t1=c, holding_max=10)


class Backtester:
    def __init__(self, frames: dict[str, pd.DataFrame], index_closes: dict[str, pd.Series],
                 charges_fn, params: BacktestParams):
        self.frames = {s: f.sort_index() for s, f in frames.items() if len(f) > 60}
        self.index = index_closes
        self.charges_fn = charges_fn  # (side, qty, price, date) -> float
        self.p = params
        self.warnings: list[str] = []

    def _sessions(self) -> list[pd.Timestamp]:
        bench = self.index.get(BENCHMARK)
        days = bench.index if bench is not None else sorted({d for f in self.frames.values() for d in f.index})
        s = pd.Timestamp(self.p.start) if self.p.start else None
        e = pd.Timestamp(self.p.end) if self.p.end else None
        return [d for d in days if (s is None or d >= s) and (e is None or d <= e)]

    def _universe(self, t: pd.Timestamp) -> list[str]:
        rows = []
        for s, f in self.frames.items():
            if t not in f.index:
                continue
            i = f.index.get_loc(t)
            if i < 210:
                continue
            win = f.iloc[i - 20 : i]
            turn = (win["close"] * win["volume"]).mean() if "turnover" not in f or win["turnover"].isna().all() \
                else win["turnover"].mean()
            if f["close"].iloc[i] < self.p.min_price or turn / 1e7 < self.p.min_turnover_cr:
                continue
            rows.append((turn, s))
        rows.sort(reverse=True)
        return [s for _, s in rows[: self.p.universe_size]]

    def _prefilter(self, sym: str, f: pd.DataFrame, i: int) -> bool:
        c = f["close"].iloc[: i + 1]
        last = float(c.iloc[-1])
        strat = self.p.strategy
        e50 = float(ema(c.iloc[-260:], 50).iloc[-1])
        if strat == "mean_reversion":
            e200 = float(ema(c.iloc[-400:], 200).iloc[-1])
            r2 = float(rsi(c.iloc[-60:], 2).iloc[-1])
            return last > e200 and r2 < 10
        if strat == "breakout":
            hi = float(f["high"].iloc[i - 20 : i].max())
            vol_ok = f["volume"].iloc[i] >= 1.5 * f["volume"].iloc[i - 20 : i].mean()
            return last > hi and vol_ok
        if last < e50:
            return False
        if strat == "momentum":
            return float(c.iloc[-1] / c.iloc[-64] - 1) > 0.10
        return True  # combined / ranking: full evaluation decides

    def run(self) -> dict:
        sessions = self._sessions()
        if len(sessions) < 40:
            raise ValueError("Not enough sessions in range for a meaningful backtest (need ≥40)")
        n = len(sessions)
        b1 = sessions[max(int(n * self.p.split[0]) - 1, 0)].date()
        b2 = sessions[max(int(n * (self.p.split[0] + self.p.split[1])) - 1, 0)].date()
        bounds = [b1, b2]
        cash = self.p.capital
        open_pos: list[dict] = []
        trades: list[BTTrade] = []
        curve: list[dict] = []
        sector_rows, regime_label, regime_conf = None, "NEUTRAL", None
        bench = self.index.get(BENCHMARK)
        for k, t in enumerate(sessions):
            td = t.date()
            # 1) settle exits that happened on t
            still = []
            for pos in open_pos:
                if pos["exit_date"] is not None and pos["exit_date"] <= td:
                    proceeds = pos["qty"] * pos["exit_price"]
                    sell_ch = self.charges_fn("SELL", pos["qty"], pos["exit_price"], pos["exit_date"])
                    cash += proceeds - sell_ch
                    gross = pos["qty"] * (pos["exit_price"] - pos["entry_price"])
                    trades.append(BTTrade(pos["symbol"], _split_label(pos["signal_date"], bounds), pos["signal_date"],
                                          pos["entry_date"], pos["entry_price"], pos["exit_date"], pos["exit_price"],
                                          pos["qty"], gross, pos["buy_ch"] + sell_ch, gross - pos["buy_ch"] - sell_ch,
                                          pos["reason"], pos["held"], pos["score"]))
                else:
                    still.append(pos)
            open_pos = still
            # 2) mark to market
            mtm = 0.0
            for pos in open_pos:
                f = self.frames[pos["symbol"]]
                px = float(f["close"].asof(t)) if pos["entry_date"] <= td else pos["entry_price"]
                mtm += pos["qty"] * px
            equity = cash + mtm
            curve.append({"date": td.isoformat(), "equity": round(equity, 2), "cash": round(cash, 2),
                          "positions": len(open_pos), "split": _split_label(td, bounds)})
            if k >= n - 1:
                break
            # 3) context as of t (weekly refresh of sector/regime to bound cost)
            if k % 5 == 0 and bench is not None:
                trunc = {nme: s[s.index <= t] for nme, s in self.index.items()}
                sector_rows = rank_sectors(trunc) or None
                if self.p.regime_aware:
                    rg = compute_regime(RegimeInputs(nifty=trunc.get(BENCHMARK), banknifty=trunc.get("Nifty Bank"),
                                                     vix=trunc.get("India VIX"), sector_rows=sector_rows))
                    regime_label, regime_conf = rg.regime, rg.confidence
            max_pos = self.p.max_positions
            if self.p.regime_aware and regime_label in ("BEARISH", "STRONG BEARISH"):
                max_pos = max(1, max_pos // 3)
            slots = max_pos - len(open_pos)
            if slots <= 0 or regime_label == "STRONG BEARISH":
                continue
            # 4) signals from data <= t
            uni = self._universe(t)
            held = {p["symbol"] for p in open_pos}
            rs_ex = {}
            if bench is not None:
                b = bench[bench.index <= t]
                for s in uni:
                    f = self.frames[s]
                    rs_ex[s] = stock_relative_strength(f["close"][f.index <= t].iloc[-140:], b.iloc[-140:])
            rs_rate = rs_percentiles(rs_ex) if rs_ex else {}
            cands = []
            for s in uni:
                if s in held:
                    continue
                f = self.frames[s]
                i = f.index.get_loc(t)
                if not self._prefilter(s, f, i):
                    continue
                hist = f.iloc[max(0, i - 299) : i + 1]
                if self.p.strategy == "mean_reversion":
                    plan = _mr_plan(hist)
                    if plan:
                        cands.append((50.0, s, plan))
                    continue
                ext = ExternalInputs(rs_rating=rs_rate.get(s), rs_excess=rs_ex.get(s),
                                     fundamentals=(None, [], [], "Excluded in backtest (point-in-time history incomplete)"),
                                     news=(None, [], [], "Excluded in backtest"), fno=(None, [], [], "Excluded in backtest"),
                                     regime=regime_label, regime_confidence=regime_conf, is_fno=False)
                ev = evaluate(s, hist, td, ext, self.p.weights, self.p.risk_cfg, self.p.excl_cfg)
                if ev.levels is None or ev.score is None or ev.rejected:
                    continue
                if self.p.strategy != "ranking" and (ev.action != "BUY" or ev.score.total < self.p.min_score):
                    continue
                lv = ev.levels
                cands.append((ev.score.total, s, TradePlan(lv.entry_low, lv.entry_high, lv.stop, lv.target1, lv.target2,
                                                           lv.target3, lv.trailing_stop_after_t1, lv.holding_max)))
            cands.sort(key=lambda x: -x[0])
            for score, s, plan in cands[: min(self.p.top_n, slots)]:
                f = self.frames[s]
                future = f[f.index > t]
                oc = simulate(plan, future)
                if oc.entry_price is None:
                    continue
                slip = self.p.slippage_bps / 1e4
                entry = oc.entry_price * (1 + slip)
                exit_px = None if oc.exit_price is None else oc.exit_price * (1 - slip)
                risk_ps = max(entry - plan.stop, entry * 0.005)
                qty = math.floor(equity * self.p.risk_pct / 100.0 / risk_ps)
                qty = min(qty, math.floor(equity * self.p.max_position_pct / 100.0 / entry))
                avg_vol = float(f["volume"][f.index <= t].iloc[-20:].mean())
                liq_cap = math.floor(avg_vol * self.p.max_volume_participation)
                if liq_cap < qty:
                    qty = liq_cap
                buy_ch = self.charges_fn("BUY", qty, entry, oc.entry_date) if qty > 0 else 0.0
                if qty <= 0 or qty * entry + buy_ch > cash:
                    continue
                cash -= qty * entry + buy_ch
                if exit_px is None:  # still open at the end of available data → mark at last close
                    last = f.iloc[-1]
                    exit_px, oc.exit_date, oc.exit_reason = float(last["close"]), last.name.date(), "end of data"
                    oc.sessions_held = len(future[future.index.date >= oc.entry_date]) - 1
                open_pos.append({"symbol": s, "signal_date": td, "entry_date": oc.entry_date, "entry_price": entry,
                                 "exit_date": oc.exit_date, "exit_price": exit_px, "qty": qty, "buy_ch": buy_ch,
                                 "reason": oc.exit_reason, "held": oc.sessions_held, "score": score})
        # Close anything left at the final equity point.
        for pos in open_pos:
            f = self.frames[pos["symbol"]]
            px = float(f["close"].asof(sessions[-1]))
            sell_ch = self.charges_fn("SELL", pos["qty"], px, sessions[-1].date())
            gross = pos["qty"] * (px - pos["entry_price"])
            trades.append(BTTrade(pos["symbol"], _split_label(pos["signal_date"], bounds), pos["signal_date"],
                                  pos["entry_date"], pos["entry_price"], sessions[-1].date(), px, pos["qty"], gross,
                                  pos["buy_ch"] + sell_ch, gross - pos["buy_ch"] - sell_ch, "end of backtest",
                                  pos["held"], pos["score"]))
        return {"curve": curve, "trades": trades, "bounds": bounds, "metrics": metrics_by_split(curve, trades),
                "warnings": [*self.warnings, "Fundamentals, news and F&O components excluded (incomplete point-in-time history).", "Estimated income tax is not deducted from the equity curve (it depends on your annual position)."]}


def _segment_metrics(curve: list[dict], trades: list[BTTrade]) -> dict:
    if len(curve) < 2:
        return {"trades": len(trades)}
    eq = pd.Series([c["equity"] for c in curve], index=pd.to_datetime([c["date"] for c in curve]))
    rets = eq.pct_change().dropna()
    days = max((eq.index[-1] - eq.index[0]).days, 1)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (365.0 / days) - 1 if eq.iloc[0] > 0 else None
    dd = (eq / eq.cummax() - 1).min()
    sd = rets.std()
    down = rets[rets < 0].std()
    pn = [t.net_pnl for t in trades]
    wins, losses = [x for x in pn if x > 0], [x for x in pn if x <= 0]
    return {
        "start": curve[0]["date"], "end": curve[-1]["date"], "start_equity": round(float(eq.iloc[0]), 2),
        "end_equity": round(float(eq.iloc[-1]), 2), "return_pct": round(float(100 * (eq.iloc[-1] / eq.iloc[0] - 1)), 2),
        "cagr": None if cagr is None else round(float(100 * cagr), 2), "max_drawdown_pct": round(100 * float(dd), 2),
        "sharpe": round(float(rets.mean() / sd * np.sqrt(252)), 2) if sd and len(rets) >= 60 else None,
        "sortino": round(float(rets.mean() / down * np.sqrt(252)), 2) if down and len(rets) >= 60 else None,
        "trades": len(trades), "win_rate": round(100 * len(wins) / len(pn), 2) if pn else None,
        "profit_factor": round(sum(wins) / -sum(losses), 3) if losses and sum(losses) < 0 else None,
        "expectancy": round(float(np.mean(pn)), 2) if pn else None,
        "avg_holding_sessions": round(float(np.mean([t.holding_sessions for t in trades if t.holding_sessions is not None])), 1)
        if any(t.holding_sessions is not None for t in trades) else None,
        "charges": round(sum(t.charges for t in trades), 2),
        "note": None if len(trades) >= 30 else "Fewer than 30 trades — statistics are not reliable.",
    }


def metrics_by_split(curve: list[dict], trades: list[BTTrade]) -> dict:
    out = {"overall": _segment_metrics(curve, trades)}
    for sp in ("train", "validation", "test"):
        seg = [c for c in curve if c["split"] == sp]
        out[sp] = _segment_metrics(seg, [t for t in trades if t.split == sp])
    return out


def decimal_charges_fn(charges_engine):
    def fn(side: str, qty: int, price: float, d: date) -> float:
        if qty <= 0:
            return 0.0
        return float(charges_engine.compute("delivery", side, Decimal(qty), Decimal(str(round(price, 2))), "NSE",
                                            trade_date=d).rounded().total)

    return fn
