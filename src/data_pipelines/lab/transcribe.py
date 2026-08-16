"""TranscribeJob — plain transformers inference against ivrit.ai's Whisper
fine-tune (design.md §3). No API/DB imports, so this is reusable later by the real
pipeline stage 4, not just this app (admin-lab.md §6)."""

import time
from typing import Any

import torch
from transformers import pipeline as hf_pipeline

from data_pipelines.lab.job import LabJob
from data_pipelines.lab.models import JobContext, TranscriptSegment, TranscriptionParams, TranscriptionResult


class TranscribeJob(LabJob[TranscriptionParams, TranscriptionResult]):
    key = "transcribe"
    description = "Whisper transcription via ivrit.ai fine-tune"
    version = "1"
    version_notes = "Initial version: plain transformers pipeline, no chunking beyond the pipeline's own default."

    @classmethod
    def params_model(cls) -> type[TranscriptionParams]:
        return TranscriptionParams

    @classmethod
    def run(cls, ctx: JobContext[TranscriptionParams]) -> TranscriptionResult:
        params = ctx.params
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        print(f"loading {params.model_id} on {device}")
        asr = hf_pipeline(
            "automatic-speech-recognition",
            model=params.model_id,
            dtype=torch.float16 if device.startswith("cuda") else torch.float32,
            device=device,
        )

        # dict[str, Any]: transformers' generate_kwargs is a passthrough straight
        # into GenerationConfig/generate(), which has no single typed shape —
        # values here span str, int, and (for initial_prompt) a torch.Tensor.
        generate_kwargs: dict[str, Any] = {"language": "he", "num_beams": params.beam_size}
        if params.initial_prompt:
            # transformers' Pipeline.tokenizer is typed as a broad union (its stub
            # covers every pipeline kind, most of which have no tokenizer at all),
            # so pyright can't see get_prompt_ids() on the ASR case specifically.
            generate_kwargs["prompt_ids"] = asr.tokenizer.get_prompt_ids(  # type: ignore[union-attr]
                params.initial_prompt, return_tensors="pt"
            )

        print(f"transcribing {ctx.audio_path}")
        start = time.monotonic()
        output = asr(str(ctx.audio_path), return_timestamps=True, generate_kwargs=generate_kwargs)
        elapsed_s = time.monotonic() - start
        print(f"transcribed in {elapsed_s:.1f}s")

        # ASR pipeline's return type is a broad union across every pipeline kind;
        # with return_timestamps=True on one audio path, it's actually always this
        # one dict shape (text + chunks) at runtime.
        chunks = output["chunks"]  # type: ignore[index]
        segments = [
            TranscriptSegment(
                start_ms=round(chunk["timestamp"][0] * 1000),
                end_ms=round((chunk["timestamp"][1] or chunk["timestamp"][0]) * 1000),
                text=chunk["text"].strip(),
            )
            for chunk in chunks
        ]
        return TranscriptionResult(
            segments=segments, model_id=params.model_id, params=params, elapsed_s=elapsed_s, device=device
        )
