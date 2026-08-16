"""DiarizeJob — pyannote.audio against ivrit.ai's diarization fine-tune (design.md
§3). No API/DB imports, same reasoning as transcribe.py."""

import time

import soundfile as sf
import torch
from pyannote.audio import Pipeline

from data_pipelines.config import get_settings
from data_pipelines.lab.job import LabJob
from data_pipelines.lab.models import DiarizationParams, DiarizationResult, DiarizationTurn, JobContext


class DiarizeJob(LabJob[DiarizationParams, DiarizationResult]):
    key = "diarize"
    description = "Speaker diarization via ivrit.ai pyannote fine-tune"
    version = "1"
    version_notes = "Initial version: pipeline defaults (AgglomerativeClustering, no manual threshold tuning)."

    @classmethod
    def params_model(cls) -> type[DiarizationParams]:
        return DiarizationParams

    @classmethod
    def run(cls, ctx: JobContext[DiarizationParams]) -> DiarizationResult:
        params = ctx.params
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"loading {params.model_id} on {device}")
        # An HF token is required even though this checkpoint is ungated:
        # pyannote.audio 4.x's SpeakerDiarization.__init__ unconditionally loads a
        # gated PLDA component regardless of clustering method (design.md §3).
        pipeline = Pipeline.from_pretrained(params.model_id, token=get_settings().hf_token.get_secret_value())
        if pipeline is None:
            raise RuntimeError(f"pyannote.audio could not load pipeline {params.model_id!r}")
        pipeline.to(device)

        print(f"diarizing {ctx.audio_path}")
        # Loaded as an in-memory waveform, not passed as a file path: pyannote.audio
        # 4.x decodes file paths via torchcodec, whose probed container duration can
        # disagree by a few hundred samples with what actually decodes for lossy
        # formats (mp3/opus) — pyannote's own crop() then raises on the mismatch.
        # A preloaded waveform sidesteps that entirely (the library's own documented
        # workaround, pyannote/audio/core/io.py's AudioFileDocString).
        data, sample_rate = sf.read(str(ctx.audio_path), dtype="float32", always_2d=True)
        waveform = torch.from_numpy(data.T)  # (channel, time), what pyannote expects
        start = time.monotonic()
        output = pipeline({"waveform": waveform, "sample_rate": sample_rate})
        elapsed_s = time.monotonic() - start
        print(f"diarized in {elapsed_s:.1f}s")

        # pyannote.audio 4.x's non-legacy SpeakerDiarization pipeline returns a
        # DiarizeOutput (diarization + exclusive_diarization + embeddings), not the
        # bare Annotation older docs/design.md §3 assumed. .speaker_diarization is
        # the Annotation with the turns this job actually wants.
        annotation = output.speaker_diarization  # type: ignore[attr-defined]
        turns = [
            DiarizationTurn(start_ms=round(turn.start * 1000), end_ms=round(turn.end * 1000), speaker=speaker)
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ]
        return DiarizationResult(
            turns=turns, model_id=params.model_id, params=params, elapsed_s=elapsed_s, device=str(device)
        )
