"""lab/merge.py's two pure functions. No DB, no fixtures — literal segments and
turns in, labels and roles out."""

from data_pipelines.lab.merge import assign_speakers, summarize_speakers
from data_pipelines.lab.models import AssignmentRule, DiarizationTurn, SpeakerRole, TranscriptSegment


def seg(start_ms: int, end_ms: int, text: str = "טקסט") -> TranscriptSegment:
    return TranscriptSegment(start_ms=start_ms, end_ms=end_ms, text=text)


def turn(start_ms: int, end_ms: int, speaker: str) -> DiarizationTurn:
    return DiarizationTurn(start_ms=start_ms, end_ms=end_ms, speaker=speaker)


class TestAssignSpeakers:
    def test_segment_inside_one_turn(self) -> None:
        turns = [turn(0, 10_000, "SPEAKER_00"), turn(10_000, 20_000, "SPEAKER_01")]
        assert assign_speakers([seg(2_000, 5_000)], turns) == ["SPEAKER_00"]

    def test_straddling_segment_goes_to_the_dominant_speaker(self) -> None:
        # 70% in SPEAKER_00 (3000..10000), 30% in SPEAKER_01 (10000..13000).
        turns = [turn(0, 10_000, "SPEAKER_00"), turn(10_000, 20_000, "SPEAKER_01")]
        assert assign_speakers([seg(3_000, 13_000)], turns) == ["SPEAKER_00"]

    def test_midpoint_and_max_overlap_can_disagree(self) -> None:
        # Takes three turns to make the two rules disagree: with only two, the
        # midpoint of a segment always sits on the side that holds most of it.
        turns = [
            turn(0, 10_000, "SPEAKER_00"),
            turn(10_000, 11_000, "SPEAKER_01"),
            turn(11_000, 20_000, "SPEAKER_02"),
        ]
        # 8000..12000: 2s in _00, 1s in _01, 1s in _02 → max overlap picks _00;
        # midpoint 10000 lands in _01.
        segment = seg(8_000, 12_000)
        assert assign_speakers([segment], turns, AssignmentRule.MAX_OVERLAP) == ["SPEAKER_00"]
        assert assign_speakers([segment], turns, AssignmentRule.MIDPOINT) == ["SPEAKER_01"]

    def test_segment_in_a_diarization_gap_falls_back_to_nearest_turn(self) -> None:
        turns = [turn(0, 5_000, "SPEAKER_00"), turn(30_000, 40_000, "SPEAKER_01")]
        # 26000..28000 overlaps neither; nearest turn *start* is 30000 (2s away)
        # vs 0 (26s away).
        assert assign_speakers([seg(26_000, 28_000)], turns) == ["SPEAKER_01"]

    def test_no_turns_leaves_every_segment_unassigned(self) -> None:
        assert assign_speakers([seg(0, 1_000), seg(1_000, 2_000)], []) == [None, None]

    def test_result_is_one_label_per_segment_in_order(self) -> None:
        turns = [turn(0, 10_000, "SPEAKER_00"), turn(10_000, 20_000, "SPEAKER_01")]
        segments = [seg(0, 1_000), seg(11_000, 12_000), seg(5_000, 6_000)]
        assert assign_speakers(segments, turns) == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]


class TestSummarizeSpeakers:
    def test_host_is_the_longest_total_not_the_first(self) -> None:
        # design.md §3's real shape: one overwhelmingly dominant label, several
        # short ones — and the host does not speak first here.
        turns = [
            turn(0, 5_000, "SPEAKER_02"),
            turn(5_000, 2_000_000, "SPEAKER_00"),
            turn(2_000_000, 2_095_000, "SPEAKER_01"),
            turn(2_100_000, 2_400_000, "SPEAKER_00"),
        ]
        summaries = {s.label: s for s in summarize_speakers(turns)}
        assert summaries["SPEAKER_00"].role is SpeakerRole.HOST
        assert summaries["SPEAKER_00"].index is None
        assert summaries["SPEAKER_02"].role is SpeakerRole.OTHER

    def test_others_are_numbered_by_first_appearance_not_duration(self) -> None:
        # SPEAKER_01 talks longer than SPEAKER_02 but starts later, so it's
        # "שואל 2" — the rule most likely to be "fixed" wrongly later.
        turns = [
            turn(0, 100_000, "SPEAKER_00"),  # host
            turn(100_000, 101_000, "SPEAKER_02"),  # first non-host to speak, briefly
            turn(101_000, 150_000, "SPEAKER_01"),  # speaks longer, but later
        ]
        summaries = {s.label: s for s in summarize_speakers(turns)}
        assert summaries["SPEAKER_02"].index == 1
        assert summaries["SPEAKER_01"].index == 2

    def test_totals_and_first_appearance_accumulate_across_turns(self) -> None:
        turns = [
            turn(1_000, 3_000, "SPEAKER_00"),
            turn(10_000, 11_500, "SPEAKER_00"),
        ]
        (host,) = summarize_speakers(turns)
        assert (host.total_ms, host.first_start_ms) == (3_500, 1_000)

    def test_host_comes_first_in_the_returned_order(self) -> None:
        turns = [turn(0, 1_000, "SPEAKER_09"), turn(1_000, 50_000, "SPEAKER_04")]
        assert [s.label for s in summarize_speakers(turns)] == ["SPEAKER_04", "SPEAKER_09"]

    def test_no_turns_is_no_speakers(self) -> None:
        assert summarize_speakers([]) == []
