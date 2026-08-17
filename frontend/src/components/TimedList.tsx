import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { usePlayback } from '../contexts/PlaybackContext'

export interface TimedItem {
  start_ms: number
  end_ms: number
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
}: {
  items: T[]
  renderRow: (item: T, index: number) => ReactNode
  emptyLabel: string
  // Extra class per row — the merged list's speaker accent (LessonResults).
  rowClassName?: (item: T, index: number) => string | undefined
  // Scroll this row into view when it changes — search jumps (§4.3).
  focusIndex?: number
}) {
  const { currentMs, seek, isPlaying } = usePlayback()
  const parentRef = useRef<HTMLDivElement>(null)

  const activeIndex = items.findIndex((item) => currentMs >= item.start_ms && currentMs < item.end_ms)

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
    overscan: 8,
  })

  // Only follow the playhead while audio is actually playing. Following while
  // paused fights the operator: @tanstack/react-virtual re-attempts a
  // scrollToIndex across measurement passes for dynamically-sized rows, so a
  // standing "scroll to the active row" instruction pulls the view back every
  // time a manual scroll re-measures — which also silently undid search jumps
  // (merge-and-search-plan.md §4.3).
  useEffect(() => {
    if (isPlaying && activeIndex >= 0) {
      virtualizer.scrollToIndex(activeIndex, { align: 'auto' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex, isPlaying])

  useEffect(() => {
    if (focusIndex !== undefined && focusIndex >= 0) {
      virtualizer.scrollToIndex(focusIndex, { align: 'center' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusIndex])

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
            >
              {renderRow(item, virtualRow.index)}
            </div>
          )
        })}
      </div>
    </div>
  )
}
