"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type Time,
  type WhitespaceData,
  type LineData,
} from "lightweight-charts";
import { useResolvedTheme } from "@/lib/theme";
import type { BarsResponse, LinePoint } from "@/lib/types";

export type IndicatorKey = "ema" | "sma" | "rsi" | "macd" | "volume" | "vwap" | "bb" | "supertrend";

/** Validated categorical slots (light / dark) — identity colours for overlay lines. */
const SERIES = {
  light: { s1: "#2a78d6", s2: "#eb6834", s3: "#4a3aa7", s4: "#e87ba4", s5: "#eda100", s6: "#1baf7a" },
  dark: { s1: "#3987e5", s2: "#d95926", s3: "#9085e9", s4: "#d55181", s5: "#c98500", s6: "#199e70" },
};

export const OVERLAY_LEGEND: Record<string, { label: string; slot: keyof (typeof SERIES)["light"]; dashed?: boolean }> = {
  ema_20: { label: "EMA 20", slot: "s1" },
  ema_50: { label: "EMA 50", slot: "s2" },
  ema_200: { label: "EMA 200", slot: "s3" },
  sma_50: { label: "SMA 50", slot: "s4" },
  vwap_20: { label: "VWAP 20", slot: "s5" },
  supertrend: { label: "Supertrend", slot: "s6" },
  bb_upper: { label: "Bollinger", slot: "s1", dashed: true },
};

export function overlayColor(key: string, theme: "light" | "dark"): string {
  const l = OVERLAY_LEGEND[key];
  return l ? SERIES[theme][l.slot] : SERIES[theme].s1;
}

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function line(points: LinePoint[] | undefined): (LineData<Time> | WhitespaceData<Time>)[] {
  return (points ?? [])
    .filter((p) => p && p.time != null)
    .map((p) => (p.value == null || !Number.isFinite(p.value) ? { time: p.time as Time } : { time: p.time as Time, value: p.value }));
}

export function CandleChart({
  data,
  indicators,
  height = 420,
  className,
}: {
  data: BarsResponse;
  indicators: Set<IndicatorKey>;
  height?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useResolvedTheme();
  const key = [...indicators].sort().join(",");

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const bars = (data.bars ?? []).filter((b) => b && b.time != null && [b.open, b.high, b.low, b.close].every((v) => Number.isFinite(v)));
    if (!bars.length) return;

    const up = cssVar("--up", "#0a8a55");
    const down = cssVar("--down", "#cf2b2b");
    const grid = cssVar("--chart-grid", "#eef1f5");
    const text = cssVar("--chart-text", "#5c6b80");
    const border = cssVar("--border", "#e1e6ed");
    const palette = SERIES[theme];
    const ind = new Set(key.split(",").filter(Boolean) as IndicatorKey[]);

    const chart: IChartApi = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: text,
        fontSize: 11,
        fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
        panes: { separatorColor: border, separatorHoverColor: border, enableResize: true },
      },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: border },
      timeScale: { borderColor: border, rightOffset: 4, timeVisible: data.interval !== "1d" },
      crosshair: { mode: CrosshairMode.Normal },
      localization: {
        locale: "en-IN",
        priceFormatter: (p: number) => p.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 }),
      },
    });

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: up,
      downColor: down,
      borderUpColor: up,
      borderDownColor: down,
      wickUpColor: up,
      wickDownColor: down,
      priceLineVisible: true,
    });
    candle.setData(bars.map((b) => ({ time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close })));

    if (ind.has("volume")) {
      const vol = chart.addSeries(HistogramSeries, {
        priceScaleId: "vol",
        priceFormat: { type: "volume" },
        lastValueVisible: false,
        priceLineVisible: false,
      });
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      vol.setData(
        bars
          .filter((b) => b.volume != null)
          .map((b) => ({
            time: b.time as Time,
            value: b.volume as number,
            color: b.close >= b.open ? `${up}55` : `${down}55`,
          })),
      );
    }

    const o = data.overlays ?? {};
    const addLine = (pts: LinePoint[] | undefined, color: string, opts: { dashed?: boolean; width?: 1 | 2; title?: string } = {}, pane = 0) => {
      if (!pts?.length) return;
      const s = chart.addSeries(
        LineSeries,
        {
          color,
          lineWidth: opts.width ?? 2,
          lineStyle: opts.dashed ? LineStyle.Dashed : LineStyle.Solid,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          title: opts.title,
        },
        pane,
      );
      s.setData(line(pts));
      return s;
    };

    if (ind.has("ema")) {
      addLine(o.ema_20, palette.s1);
      addLine(o.ema_50, palette.s2);
      addLine(o.ema_200, palette.s3);
    }
    if (ind.has("sma")) addLine(o.sma_50, palette.s4);
    if (ind.has("vwap")) addLine(o.vwap_20, palette.s5);
    if (ind.has("bb")) {
      addLine(o.bb_upper, palette.s1, { dashed: true, width: 1 });
      addLine(o.bb_lower, palette.s1, { dashed: true, width: 1 });
    }
    if (ind.has("supertrend")) addLine(o.supertrend, palette.s6);

    const p = data.panes ?? {};
    let pane = 1;
    if (ind.has("rsi") && p.rsi_14?.length) {
      const rsi = addLine(p.rsi_14, palette.s3, { title: "RSI 14" }, pane);
      if (rsi) {
        rsi.createPriceLine({ price: 70, color: down, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "" });
        rsi.createPriceLine({ price: 30, color: up, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "" });
      }
      pane += 1;
    }
    if (ind.has("macd") && (p.macd?.length || p.macd_hist?.length)) {
      if (p.macd_hist?.length) {
        const h = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane);
        h.setData(
          p.macd_hist
            .filter((x) => x?.time != null)
            .map((x) =>
              x.value == null ? { time: x.time as Time } : { time: x.time as Time, value: x.value, color: x.value >= 0 ? `${up}99` : `${down}99` },
            ),
        );
      }
      addLine(p.macd, palette.s1, { title: "MACD" }, pane);
      addLine(p.macd_signal, palette.s2, { title: "Signal", width: 1 }, pane);
      pane += 1;
    }

    const panes = chart.panes();
    if (panes.length > 1) {
      panes[0].setStretchFactor(3);
      for (let i = 1; i < panes.length; i++) panes[i].setStretchFactor(1);
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, key, theme]);

  const nBars = data.bars?.length ?? 0;
  return (
    <div
      ref={ref}
      className={className}
      style={{ height }}
      role="img"
      aria-label={`Candlestick price chart with ${nBars} bars${key ? `; indicators: ${key}` : ""}`}
    />
  );
}
