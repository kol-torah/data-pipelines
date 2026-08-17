// Mirrors lab/models.py's TranscriptSegment/TranscriptionResult and
// DiarizationTurn/DiarizationResult. Same reasoning as JobRunPage's
// *ParamsInput types: job_type-specific result shapes are opaque dict[str, Any]
// at the generic /api/lab/jobs boundary by design (admin-lab.md §5.2), so they
// never appear in the OpenAPI schema — hand-typed here instead of generated.

export interface TranscriptSegment {
  start_ms: number
  end_ms: number
  text: string
}

export interface TranscriptionResult {
  segments: TranscriptSegment[]
  model_id: string
  elapsed_s: number
  device: string
}

export interface DiarizationTurn {
  start_ms: number
  end_ms: number
  speaker: string
}

export interface DiarizationResult {
  turns: DiarizationTurn[]
  model_id: string
  elapsed_s: number
  device: string
}

// Mirrors lab/models.py's merge models. `speaker` is the raw pyannote label;
// `speakers` maps it to a role, and the Hebrew strings ("מנחה" / "שואל N") are
// rendered here rather than stored, so merge.py stays reusable by a non-UI
// pipeline stage (merge-and-search-plan.md §2.3).
export interface MergedSegment {
  start_ms: number
  end_ms: number
  text: string
  speaker: string | null
}

export interface SpeakerSummary {
  label: string
  role: 'host' | 'other'
  index: number | null
  total_ms: number
  first_start_ms: number
}

export interface MergeResult {
  segments: MergedSegment[]
  speakers: SpeakerSummary[]
  source_job_ids: Record<string, number>
  elapsed_s: number
}
