import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { createJob, getJob, listLabLessons, listLessonJobs } from '../api/lab'
import type { LabJob } from '../api/lab'
import { JobStatusBadge } from '../components/JobStatusBadge'
import { LessonResults } from '../components/LessonResults'

// Mirrors lab/models.py's TranscriptionParams/DiarizationParams (server-side
// dict[str, Any] at the generic /api/lab/jobs boundary by design, AL §5.2 — these
// two shapes are hand-typed here rather than OpenAPI-generated because neither is
// ever a typed request/response body itself).
interface TranscriptionParamsInput {
  model_id: string
  beam_size: number
  initial_prompt: string
}

interface DiarizationParamsInput {
  model_id: string
}

const JOB_TYPE_DEFS = [
  {
    key: 'transcribe',
    label: 'תמלול',
    defaultParams: (): TranscriptionParamsInput => ({
      model_id: 'ivrit-ai/whisper-large-v3-turbo',
      beam_size: 5,
      initial_prompt: '',
    }),
  },
  {
    key: 'diarize',
    label: 'זיהוי דוברים',
    defaultParams: (): DiarizationParamsInput => ({ model_id: 'ivrit-ai/pyannote-speaker-diarization-3.1' }),
  },
] as const

export function JobRunPage() {
  const { lessonId } = useParams()
  const id = Number(lessonId)

  const { data: lessons } = useQuery({
    queryKey: ['lab', 'lessons', 'byId', id],
    queryFn: () => listLabLessons({ lessonIds: [id] }),
  })
  const lesson = lessons?.[0]

  // Polled independently of each JobTypePanel's own per-job status query below
  // (which additionally does the self-heal check via GET /jobs/{id}) — this is
  // only what feeds the results section fresh result_json once a job finishes,
  // and only needs to poll while something might still be running.
  const { data: jobs } = useQuery({
    queryKey: ['lab', 'lessons', id, 'jobs'],
    queryFn: () => listLessonJobs(id),
    refetchInterval: (query) => (query.state.data?.some((j) => j.status === 'running') ? 3000 : false),
  })
  const transcribeJob = jobs?.find((j) => j.job_type === 'transcribe')
  const diarizeJob = jobs?.find((j) => j.job_type === 'diarize')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--kt-space-5)' }}>
      <div className="kt-card">
        <h2>{lesson?.title_he ?? 'טוען...'}</h2>
        {lesson && (
          <p className="kt-meta">
            {lesson.rabbi_name_he} — {lesson.series_name_he}
            {(lesson.recorded_at ?? lesson.published_at) && (
              <>
                {' · '}
                <span className="kt-time">
                  {new Date(lesson.recorded_at ?? lesson.published_at!).toLocaleDateString('he-IL')}
                </span>
              </>
            )}
          </p>
        )}
      </div>

      {jobs !== undefined &&
        JOB_TYPE_DEFS.map((def) => {
          const latest = jobs.find((j) => j.job_type === def.key)
          return (
            <JobTypePanel
              key={def.key}
              lessonId={id}
              jobTypeKey={def.key}
              label={def.label}
              defaultParams={def.defaultParams()}
              initialJob={latest}
            />
          )
        })}

      {lesson && <LessonResults lessonId={id} transcribeJob={transcribeJob} diarizeJob={diarizeJob} />}
    </div>
  )
}

function JobTypePanel({
  lessonId,
  jobTypeKey,
  label,
  defaultParams,
  initialJob,
}: {
  lessonId: number
  jobTypeKey: string
  label: string
  defaultParams: TranscriptionParamsInput | DiarizationParamsInput
  initialJob: LabJob | undefined
}) {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<number | undefined>(initialJob?.id)
  const [showForm, setShowForm] = useState(initialJob === undefined)
  const [paramsText, setParamsText] = useState(() => JSON.stringify(defaultParams, null, 2))
  const [formError, setFormError] = useState<string | null>(null)

  const { data: job } = useQuery({
    queryKey: ['lab', 'job', jobId],
    queryFn: () => getJob(jobId as number),
    enabled: jobId !== undefined,
    initialData: jobId === initialJob?.id ? initialJob : undefined,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  })

  const launchMutation = useMutation({
    mutationFn: () => {
      const params = JSON.parse(paramsText) as Record<string, unknown>
      return createJob({ lesson_id: lessonId, job_type: jobTypeKey, params })
    },
    onSuccess: (created) => {
      setFormError(null)
      setJobId(created.id)
      setShowForm(false)
      // So the parent's `jobs` poll (LessonResults' data source) picks up the
      // new running job immediately instead of waiting for its next own trigger.
      queryClient.invalidateQueries({ queryKey: ['lab', 'lessons', lessonId, 'jobs'] })
    },
    onError: (e) => setFormError(e instanceof Error ? e.message : String(e)),
  })

  const isRunning = job?.status === 'running'

  return (
    <div className="kt-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3>{label}</h3>
        {job && <JobStatusBadge status={job.status} />}
      </div>

      {job && !showForm && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--kt-space-3)' }}>
          <p className="kt-meta">
            <span className="kt-time">{job.model_id}</span> · הופעל{' '}
            <span className="kt-time">{new Date(job.started_at).toLocaleString('he-IL')}</span>
          </p>
          {isRunning && <p>מריץ...</p>}
          {job.status === 'failed' && (
            <p className="kt-error" dir="ltr" style={{ textAlign: 'left', unicodeBidi: 'isolate' }}>
              {job.error}
            </p>
          )}
          {job.status === 'done' && job.result_json && (
            <details>
              <summary>תוצאה</summary>
              <pre
                dir="ltr"
                style={{
                  whiteSpace: 'pre-wrap',
                  fontSize: 'var(--kt-size-small)',
                  textAlign: 'left',
                  unicodeBidi: 'isolate',
                }}
              >
                {JSON.stringify(job.result_json, null, 2)}
              </pre>
            </details>
          )}
          {job.log && (
            <details>
              <summary>לוג</summary>
              <pre
                dir="ltr"
                style={{
                  whiteSpace: 'pre-wrap',
                  fontSize: 'var(--kt-size-small)',
                  textAlign: 'left',
                  unicodeBidi: 'isolate',
                }}
              >
                {job.log}
              </pre>
            </details>
          )}
          {!isRunning && (
            <button
              type="button"
              className="kt-btn kt-btn--secondary"
              onClick={() => {
                setShowForm(true)
                // Prefill with the params this job actually ran with, not the
                // hardcoded defaults — the form's own "איפוס" button covers
                // wanting the defaults back.
                setParamsText(JSON.stringify(job.params, null, 2))
              }}
            >
              הרץ שוב
            </button>
          )}
        </div>
      )}

      {showForm && (
        <div className="kt-form">
          <div className="kt-field">
            <label htmlFor={`${jobTypeKey}-params`}>פרמטרים (JSON)</label>
            <textarea
              id={`${jobTypeKey}-params`}
              dir="ltr"
              rows={5}
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              // admin.css's `.kt-field textarea[dir="ltr"] { text-align: end }` is
              // meant for short single-line English fields (hug the RTL form's
              // right edge) — right-aligning every line of multi-line JSON makes
              // it read as RTL-flowing, which is what this overrides.
              style={{ textAlign: 'left', fontFamily: 'var(--kt-font-mono)' }}
              // Field names (model_id, beam_size, initial_prompt) aren't English
              // prose, so the browser's spellchecker just adds noise here.
              spellCheck={false}
            />
          </div>
          {formError && <p className="kt-error">{formError}</p>}
          <div className="kt-form-actions">
            <button type="button" className="kt-btn" onClick={() => launchMutation.mutate()}>
              הרץ
            </button>
            <button
              type="button"
              className="kt-btn kt-btn--secondary"
              onClick={() => setParamsText(JSON.stringify(defaultParams, null, 2))}
            >
              איפוס לברירת מחדל
            </button>
            {/* Only when there's a previous job to go back to — the very first
                launch (no prior job yet) has no display behind the form to
                return to. */}
            {job && (
              <button type="button" className="kt-btn kt-btn--secondary" onClick={() => setShowForm(false)}>
                ביטול
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
