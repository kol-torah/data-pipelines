import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

// Shared playback position (admin-lab.md §4.8): the <audio> element's currentTime,
// read/written by the player, both timed lists, and the jump control. Plain
// useState, no state-management library — one value shared by a handful of
// siblings under one provider (admin-lab-plan.md §5.2).
export interface PlaybackContextValue {
  currentMs: number
  durationMs: number
  isPlaying: boolean
  /** Where the columns are looking, when nobody is playing — see TimedList's
   *  scroll sync (run-comparison-plan.md §4.2). Null until something publishes one. */
  anchorMs: number | null
  /** Which column published `anchorMs`. A column ignores its own anchors, which is
   *  what stops two synced columns from chasing each other. */
  anchorSource: string | null
  setAnchor: (ms: number, source: string) => void
  play: () => void
  pause: () => void
  seek: (ms: number) => void
  seekFraction: (fraction: number) => void
  jump: (deltaMs: number) => void
}

const PlaybackContext = createContext<PlaybackContextValue | null>(null)

export function PlaybackProvider({ src, children }: { src: string; children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [currentMs, setCurrentMs] = useState(0)
  const [durationMs, setDurationMs] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [anchor, setAnchorState] = useState<{ ms: number; source: string } | null>(null)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const onTimeUpdate = () => setCurrentMs(audio.currentTime * 1000)
    const onLoadedMetadata = () => setDurationMs(audio.duration * 1000)
    const onPlay = () => setIsPlaying(true)
    const onPause = () => setIsPlaying(false)
    audio.addEventListener('timeupdate', onTimeUpdate)
    audio.addEventListener('loadedmetadata', onLoadedMetadata)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate)
      audio.removeEventListener('loadedmetadata', onLoadedMetadata)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
    }
  }, [])

  const seek = (ms: number) => {
    const audio = audioRef.current
    if (!audio) return
    const clamped = Math.min(Math.max(ms, 0), durationMs || ms)
    audio.currentTime = clamped / 1000
    setCurrentMs(clamped) // immediate feedback, ahead of the next timeupdate
  }

  const value: PlaybackContextValue = {
    currentMs,
    durationMs,
    isPlaying,
    anchorMs: anchor?.ms ?? null,
    anchorSource: anchor?.source ?? null,
    setAnchor: (ms, source) => setAnchorState({ ms, source }),
    play: () => void audioRef.current?.play(),
    pause: () => audioRef.current?.pause(),
    seek,
    seekFraction: (fraction) => seek(fraction * durationMs),
    jump: (deltaMs) => seek(currentMs + deltaMs),
  }

  return (
    <PlaybackContext.Provider value={value}>
      {/* No native controls — the vendored .kt-player-row markup (AudioPlayer) is
          the controls (admin-lab-plan.md §5.2). */}
      <audio ref={audioRef} src={src} preload="metadata" style={{ display: 'none' }} />
      {children}
    </PlaybackContext.Provider>
  )
}

export function usePlayback(): PlaybackContextValue {
  const ctx = useContext(PlaybackContext)
  if (!ctx) throw new Error('usePlayback must be used within a PlaybackProvider')
  return ctx
}
