"""TranscribeJob — plain transformers inference against ivrit.ai's Whisper
fine-tune (design.md §3). No API/DB imports, so this is reusable later by the real
pipeline stage 4, not just this app (admin-lab.md §6)."""

import copy
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

        # One explicit GenerationConfig, not loose kwargs alongside the pipeline's
        # own default one. transformers' ASR pipeline always injects
        # self.generation_config into the generate() call unless the caller
        # already supplied one (automatic_speech_recognition.py) — passing
        # language/num_beams as separate generate_kwargs on top of that collides
        # with it (newer transformers versions warn: "pass either a
        # generation_config object OR all generation parameters explicitly, but
        # not both"). Copying the pipeline's own config (not building one from
        # scratch) keeps Whisper-specific fields it already carries — e.g.
        # forced_decoder_ids, suppress_tokens — that a fresh GenerationConfig()
        # wouldn't have.
        generation_config = copy.deepcopy(asr.generation_config)
        # GenerationConfig accepts arbitrary kwargs at construction (**kwargs), so
        # its stub doesn't declare these Whisper-specific fields.
        generation_config.language = "he"  # type: ignore[attr-defined]
        generation_config.task = "transcribe"  # type: ignore[attr-defined]
        generation_config.num_beams = params.beam_size

        # dict[str, Any]: transformers' generate_kwargs is a passthrough straight
        # into generate(), which has no single typed shape — values here span a
        # GenerationConfig and (for initial_prompt) a torch.Tensor.
        generate_kwargs: dict[str, Any] = {"generation_config": generation_config}
        if params.initial_prompt:
            # transformers' Pipeline.tokenizer is typed as a broad union (its stub
            # covers every pipeline kind, most of which have no tokenizer at all),
            # so pyright can't see get_prompt_ids() on the ASR case specifically.
            #
            # get_prompt_ids() always returns a CPU tensor — the tokenizer has no
            # notion of which device the model is on — so on a CUDA run this has
            # to be moved explicitly, or generate()'s torch.cat of prompt_ids
            # against the (GPU) decoder input ids fails with a device mismatch.
            generate_kwargs["prompt_ids"] = asr.tokenizer.get_prompt_ids(  # type: ignore[union-attr]
                params.initial_prompt, return_tensors="pt"
            ).to(device)

        print(f"transcribing {ctx.audio_path}")
        start = time.monotonic()
        output = asr(str(ctx.audio_path), return_timestamps=True, generate_kwargs=generate_kwargs)
        elapsed_s = time.monotonic() - start
        print(f"transcribed in {elapsed_s:.1f}s")

        # ASR pipeline's return type is a broad union across every pipeline kind;
        # with return_timestamps=True on one audio path, it's actually always this
        # one dict shape (text + chunks) at runtime.
        chunks = output["chunks"]  # type: ignore[index]
        segments = []
        for chunk in chunks:
            chunk_start, chunk_end = chunk["timestamp"]
            # Whisper can fail to predict a timestamp token at either edge of a
            # chunk (not just the end — confirmed in practice, not just in
            # theory: a short beam_size + initial_prompt combination produced a
            # None *start* here). A chunk missing both isn't placeable at all;
            # one missing is filled in from the other.
            if chunk_start is None and chunk_end is None:
                print(f"skipping chunk with no timestamps at all: {chunk['text']!r}")
                continue
            chunk_start = chunk_start if chunk_start is not None else chunk_end
            chunk_end = chunk_end if chunk_end is not None else chunk_start
            segments.append(
                TranscriptSegment(
                    start_ms=round(chunk_start * 1000), end_ms=round(chunk_end * 1000), text=chunk["text"].strip()
                )
            )
        return TranscriptionResult(
            segments=segments, model_id=params.model_id, params=params, elapsed_s=elapsed_s, device=device
        )
