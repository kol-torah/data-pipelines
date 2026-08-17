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
}: {
  items: T[]
  renderRow: (item: T) => ReactNode
  emptyLabel: string
}) {
  const { currentMs, seek } = usePlayback()
  const parentRef = useRef<HTMLDivElement>(null)

  const activeIndex = items.findIndex((item) => currentMs >= item.start_ms && currentMs < item.end_ms)

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
    overscan: 8,
  })

  useEffect(() => {
    if (activeIndex >= 0) {
      virtualizer.scrollToIndex(activeIndex, { align: 'auto' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex])

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
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}>
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const item = items[virtualRow.index]
          const active = virtualRow.index === activeIndex
          return (
            <div
              key={virtualRow.index}
              ref={virtualizer.measureElement}
              data-index={virtualRow.index}
              className="kt-row"
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
              {renderRow(item)}
            </div>
          )
        })}
      </div>
    </div>
  )
}
