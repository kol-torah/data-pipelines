import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { usePlayback } from '../contexts/PlaybackContext'

export interface TimedItem {
  start_ms: number
  end_ms: number
}

/** The row that holds `ms` — or, if it falls in a gap between rows, the one
 *  starting after it, so a moment of silence still anchors somewhere sensible. */
function indexAtTime(items: TimedItem[], ms: number): number {
  if (items.length === 0) return -1
  const after = items.findIndex((item) => item.end_ms > ms)
  return after === -1 ? items.length - 1 : after
}

function fractionThrough(item: TimedItem, ms: number): number {
  const span = item.end_ms - item.start_ms
  if (span <= 0) return 0
  return Math.min(1, Math.max(0, (ms - item.start_ms) / span))
}

// Shared by SegmentList and TurnList (admin-lab-plan.md §5.2) — both are
// "virtualized list of [start_ms, end_ms) rows synced to one playback
// position," differing only in what a row renders. A two-hour Q&A lesson
// produces hundreds of rows (admin-lab.md §4.8), hence @tanstack/react-virtual
// rather than rendering every row.
export function TimedList<T extends TimedItem>({
  items,
  renderRow,
  emptyLabel,
  rowClassName,
  focusIndex,
  syncId,
  onHoverItem,
}: {
  items: T[]
  renderRow: (item: T, index: number) => ReactNode
  emptyLabel: string
  // Extra class per row — the merged list's speaker accent (LessonResults).
  rowClassName?: (item: T, index: number) => string | undefined
  // Scroll this row into view when it changes — search jumps (§4.3).
  focusIndex?: number
  // Identity for timestamp scroll sync across comparison columns. Omit for a
  // standalone list (run-comparison-plan.md §4.2).
  syncId?: string
  // Row under the pointer, so sibling columns can mark the same moment. null on
  // leave.
  onHoverItem?: (item: T | null) => void
}) {
  const { currentMs, seek, isPlaying, anchorMs, anchorSource, setAnchor } = usePlayback()
  const parentRef = useRef<HTMLDivElement>(null)
  // Scrolls this component performs itself must not be mistaken for the operator
  // scrolling, or two synced columns publish anchors at each other forever.
  const programmaticUntil = useRef(0)
  const scrollFrame = useRef(0)

  const activeIndex = items.findIndex((item) => currentMs >= item.start_ms && currentMs < item.end_ms)

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
    overscan: 8,
    // Without this, every scroll-driven update runs through flushSync, which
    // React rejects when the scroll was started from an effect — two synced
    // columns (run-comparison-plan.md §4.2) do exactly that, one scrolling the
    // other. The option exists for this; the cost is that a fast scroll may show
    // a frame of unfilled rows, which `overscan` above already covers.
    useFlushSync: false,
  })

  const scrollToIndex = (index: number, align: 'auto' | 'center' | 'start') => {
    programmaticUntil.current = performance.now() + 250
    virtualizer.scrollToIndex(index, { align })
  }


  // Only follow the playhead while audio is actually playing. Following while
  // paused fights the operator: @tanstack/react-virtual re-attempts a
  // scrollToIndex across measurement passes for dynamically-sized rows, so a
  // standing "scroll to the active row" instruction pulls the view back every
  // time a manual scroll re-measures — which also silently undid search jumps
  // (merge-and-search-plan.md §4.3).
  useEffect(() => {
    if (isPlaying && activeIndex >= 0) {
      scrollToIndex(activeIndex, 'auto')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex, isPlaying])

  useEffect(() => {
    if (focusIndex !== undefined && focusIndex >= 0) {
      scrollToIndex(focusIndex, 'center')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusIndex])

  // Follow an anchor somebody else published: put *that moment of the lesson* at
  // this column's top edge. Columns have different row counts and different
  // boundaries, so syncing by row index would drift immediately — the timeline is
  // the only thing they share. Aligning the containing row's top isn't enough
  // either: a 20-second segment would land the columns up to 20 seconds apart, so
  // the offset is interpolated *within* the row.
  useEffect(() => {
    if (syncId === undefined || anchorMs === null || anchorSource === syncId) return
    if (isPlaying) return // playback already drives every column
    const index = indexAtTime(items, anchorMs)
    if (index < 0) return
    const rowOffset = virtualizer.getOffsetForIndex(index, 'start')?.[0]
    if (rowOffset === undefined) return
    const item = items[index]
    const size = virtualizer.measurementsCache[index]?.size ?? 64
    programmaticUntil.current = performance.now() + 250
    virtualizer.scrollToOffset(rowOffset + fractionThrough(item, anchorMs) * size)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchorMs, anchorSource])

  const handleScroll = () => {
    if (syncId === undefined || isPlaying) return
    if (performance.now() < programmaticUntil.current) return
    if (scrollFrame.current) return
    scrollFrame.current = requestAnimationFrame(() => {
      scrollFrame.current = 0
      const offset = parentRef.current?.scrollTop
      if (offset === undefined) return
      // The first *rendered* row is not the first *visible* row: `overscan` keeps
      // 8 rows above the viewport mounted, so publishing getVirtualItems()[0]
      // announced a moment ~8 rows earlier than the one on screen, and every
      // follower scrolled that much too far back. Take the row the top edge
      // actually cuts through, and interpolate where inside it the edge falls.
      const top = virtualizer.getVirtualItems().find((row) => row.end > offset)
      if (top === undefined) return
      const item = items[top.index]
      const through = top.size > 0 ? Math.min(1, Math.max(0, (offset - top.start) / top.size)) : 0
      setAnchor(item.start_ms + through * (item.end_ms - item.start_ms), syncId)
    })
  }

  if (items.length === 0) {
    return <p className="kt-meta">{emptyLabel}</p>
  }

  return (
    // marginInline/paddingInline cancel out visually (content lands back at its
    // original position) but open up --kt-space-4 of padding on each side —
    // overflow-y:auto here also forces overflow-x to clip (a CSS overflow-spec
    // quirk: "visible" on one axis becomes "auto" when the other isn't
    // "visible"), which would otherwise cut off .kt-row[aria-current]'s own
    // negative-margin "bleed to the card edge" (base.css) right at this
    // container's edge. Clipping happens at the padding edge, not the content
    // edge, so the bleed lands in this new padding buffer instead of getting cut.
    <div
      ref={parentRef}
      onScroll={handleScroll}
      className="kt-list"
      style={{
        height: 480,
        overflowY: 'auto',
        position: 'relative',
        marginInline: 'calc(-1 * var(--kt-space-4))',
        paddingInline: 'var(--kt-space-4)',
      }}
    >
      {/* flexShrink: 0 is load-bearing, not defensive. The vendored `.kt-list`
          is `display: flex; flex-direction: column` (base.css), which makes this
          spacer a flex item — and flexbox then shrinks its virtual height
          (~82000px on a long lesson) down to the height of the rows that happen
          to be rendered. The scrollbar ends up describing the rendered window
          instead of the whole list, and every scrollToIndex lands short and has
          to converge by inches. */}
      <div
        style={{
          height: virtualizer.getTotalSize(),
          flexShrink: 0,
          position: 'relative',
          width: '100%',
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const item = items[virtualRow.index]
          const active = virtualRow.index === activeIndex
          return (
            <div
              key={virtualRow.index}
              ref={virtualizer.measureElement}
              data-index={virtualRow.index}
              className={['kt-row', rowClassName?.(item, virtualRow.index)].filter(Boolean).join(' ')}
              aria-current={active ? 'true' : undefined}
              style={{
                position: 'absolute',
                top: 0,
                insetInlineStart: 0,
                insetInlineEnd: 0,
                transform: `translateY(${virtualRow.start}px)`,
              }}
              onClick={() => seek(item.start_ms)}
              onMouseEnter={onHoverItem ? () => onHoverItem(item) : undefined}
              onMouseLeave={onHoverItem ? () => onHoverItem(null) : undefined}
            >
              {renderRow(item, virtualRow.index)}
            </div>
          )
        })}
      </div>
    </div>
  )
}
