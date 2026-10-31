const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

export function chartViewport(total, start = 0, count = total) {
  count = clamp(Math.round(count), Math.min(12, total), total);
  // Permite espaço vazio nas bordas ao arrastar, mantendo ao menos uma vela visível.
  return { start: clamp(Math.round(start), 1 - count, total - 1), count };
}

export function zoomViewport(total, view, factor, anchor = .5) {
  const count = chartViewport(total, view.start, view.count * factor).count;
  return chartViewport(total, view.start + (view.count - count) * clamp(anchor, 0, 1), count);
}
