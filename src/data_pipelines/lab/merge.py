"""MergeJob — assigns a diarization speaker to every transcript segment
(design.md §3's deferred merge step, admin-lab.md §5.3).

No API/DB imports, same reasoning as transcribe.py/diarize.py: assign_speakers()
and summarize_speakers() are plain functions over the two result models, so the
real pipeline stage can import them unchanged once a configuration wins
(design.md §8.5).
"""

import time

from data_pipelines.lab.job import LabJob
from data_pipelines.lab.models import (
    AssignmentRule,
    DiarizationResult,
    DiarizationTurn,
    JobContext,
    MergedSegment,
    MergeParams,
    MergeResult,
    SpeakerRole,
    SpeakerSummary,
    TranscriptionResult,
    TranscriptSegment,
)


def _overlap_ms(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def assign_speakers(
    segments: list[TranscriptSegment],
    turns: list[DiarizationTurn],
    assignment: AssignmentRule = AssignmentRule.MAX_OVERLAP,
) -> list[str | None]:
    """One speaker label (or None) per segment, in the same order.

    Segments and turns come from two independent models, so their boundaries
    don't line up: a segment routinely straddles a speaker change. MAX_OVERLAP
    gives it to whoever holds most of it; MIDPOINT to whoever holds its middle.
    Neither splits the segment — that needs word-level timestamps, which
    TranscribeJob doesn't currently request (see the plan's §2.2).
    """
    if not turns:
        return [None] * len(segments)

    labels: list[str | None] = []
    for segment in segments:
        if assignment is AssignmentRule.MIDPOINT:
            midpoint = (segment.start_ms + segment.end_ms) // 2
            containing = next((t for t in turns if t.start_ms <= midpoint < t.end_ms), None)
            labels.append(containing.speaker if containing is not None else _nearest(turns, segment).speaker)
            continue

        best: DiarizationTurn | None = None
        best_overlap = 0
        for turn in turns:
            overlap = _overlap_ms(segment.start_ms, segment.end_ms, turn.start_ms, turn.end_ms)
            # Strictly greater, so a tie goes to the earlier turn — arbitrary but
            # deterministic, which is what matters for a re-runnable job.
            if overlap > best_overlap:
                best, best_overlap = turn, overlap
        labels.append((best or _nearest(turns, segment)).speaker)
    return labels


def _nearest(turns: list[DiarizationTurn], segment: TranscriptSegment) -> DiarizationTurn:
    """Fallback for a segment that overlaps no turn at all — diarization leaves
    gaps (silence, music, speech it dropped), and a transcript segment can land
    entirely inside one."""
    return min(turns, key=lambda t: abs(t.start_ms - segment.start_ms))


def summarize_speakers(turns: list[DiarizationTurn]) -> list[SpeakerSummary]:
    """Label → role mapping. Host is the label with the most total speaking time
    (design.md §3: on the test lesson the host was one overwhelmingly dominant
    label, 2314s vs. 95s for the next). The rest are numbered by *first
    appearance*, not by duration — "שואל 1" should mean the first questioner as a
    listener perceives them, not whoever happened to talk most.

    Unproven heuristic, deliberately re-runnable rather than authoritative
    (admin-lab.md §4.7, as revised by the plan's §0.2) — the raw labels stay in
    the result so it can be checked rather than trusted.
    """
    total_ms: dict[str, int] = {}
    first_start_ms: dict[str, int] = {}
    for turn in turns:
        total_ms[turn.speaker] = total_ms.get(turn.speaker, 0) + (turn.end_ms - turn.start_ms)
        if turn.speaker not in first_start_ms or turn.start_ms < first_start_ms[turn.speaker]:
            first_start_ms[turn.speaker] = turn.start_ms
    if not total_ms:
        return []

    host = max(total_ms, key=lambda label: (total_ms[label], -first_start_ms[label]))
    others = sorted((label for label in total_ms if label != host), key=lambda label: first_start_ms[label])
    index_by_label = {label: i for i, label in enumerate(others, start=1)}

    return [
        SpeakerSummary(
            label=label,
            role=SpeakerRole.HOST if label == host else SpeakerRole.OTHER,
            index=index_by_label.get(label),
            total_ms=total_ms[label],
            first_start_ms=first_start_ms[label],
        )
        # Host first, then the others in numbering order — the order the UI
        # would want to list them in anyway.
        for label in [host, *others]
    ]


class MergeJob(LabJob[MergeParams, MergeResult]):
    key = "merge"
    description = "Assign diarization speakers to transcript segments"
    version = "1"
    version_notes = "Initial version: max-overlap assignment, host = longest total speaking time."
    needs_audio = False

    @classmethod
    def params_model(cls) -> type[MergeParams]:
        return MergeParams

    @classmethod
    def run(cls, ctx: JobContext[MergeParams]) -> MergeResult:
        params = ctx.params
        # Same edge-of-the-system validation run_job.py does for params: the
        # source results arrive as opaque dicts (JobContext.source_results) and
        # get their real type attached here, once.
        transcription = TranscriptionResult.model_validate(ctx.source_results["transcription"])
        diarization = DiarizationResult.model_validate(ctx.source_results["diarization"])
        print(
            f"merging {len(transcription.segments)} transcript segments with "
            f"{len(diarization.turns)} diarization turns ({params.assignment})"
        )

        start = time.monotonic()
        labels = assign_speakers(transcription.segments, diarization.turns, params.assignment)
        speakers = summarize_speakers(diarization.turns)
        elapsed_s = time.monotonic() - start

        unassigned = sum(1 for label in labels if label is None)
        host = next((s.label for s in speakers if s.role is SpeakerRole.HOST), None)
        print(f"host={host}, {len(speakers)} speakers, {unassigned} segments unassigned, {elapsed_s:.2f}s")

        return MergeResult(
            segments=[
                MergedSegment(start_ms=s.start_ms, end_ms=s.end_ms, text=s.text, speaker=label)
                for s, label in zip(transcription.segments, labels, strict=True)
            ],
            speakers=speakers,
            params=params,
            source_job_ids=params.source_job_ids(),
            elapsed_s=elapsed_s,
        )
