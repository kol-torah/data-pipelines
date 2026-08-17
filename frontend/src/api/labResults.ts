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
