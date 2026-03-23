"""
Shared Ollama-backed transcript analysis for desktop and web workflows.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import ollama


DEFAULT_ANALYSIS_MODEL = "gemma3:4b"
MODEL_FALLBACKS = ["gemma3:4b", "qwen3:8b", "llama3.1:8b"]
DEFAULT_HUMOR_STYLE = "dry"
DEFAULT_PRESET = "caption_ideas"
MAX_DIGEST_CHARS = 6000
MAX_SOURCE_CHARS = 12000


@dataclass
class AnalysisItem:
    text: str
    humor_style: str
    score: float
    why_it_works: str
    risk_flags: List[str] = field(default_factory=list)


@dataclass
class PresetResult:
    preset: str
    humor_style: str
    model: str
    digest: str
    items: List[AnalysisItem]
    custom_prompt: str = ""
    custom_response: str = ""
    raw_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preset": self.preset,
            "humor_style": self.humor_style,
            "model": self.model,
            "digest": self.digest,
            "items": [asdict(item) for item in self.items],
            "custom_prompt": self.custom_prompt,
            "custom_response": self.custom_response,
            "raw_output": self.raw_output,
        }


@dataclass
class AnalysisResult:
    summary: str
    key_points: List[str]
    quotes: List[str]
    topics: List[str]
    sentiment: str
    custom_analysis: Dict[str, Any]


@dataclass(frozen=True)
class HumorStyleProfile:
    name: str
    label: str
    rules: List[str]
    negative_rules: List[str]

    def as_prompt_block(self) -> str:
        rules_text = "\n".join(f"- {rule}" for rule in self.rules)
        negative_text = "\n".join(f"- {rule}" for rule in self.negative_rules)
        return (
            f"Style: {self.label}\n"
            f"Positive rules:\n{rules_text}\n"
            f"Negative rules:\n{negative_text}"
        )


@dataclass(frozen=True)
class AnalysisPreset:
    name: str
    label: str
    output_label: str
    instructions: str
    count: int


HUMOR_STYLE_REGISTRY: Dict[str, HumorStyleProfile] = {
    "dry": HumorStyleProfile(
        name="dry",
        label="Dry",
        rules=[
            "Use understated irony and restraint.",
            "Keep lines compact and easy to read on screen.",
            "Prefer clever phrasing over loud exaggeration.",
        ],
        negative_rules=[
            "No emojis.",
            "No hashtags.",
            "Do not explain the joke in the final line.",
        ],
    ),
    "absurd": HumorStyleProfile(
        name="absurd",
        label="Absurd",
        rules=[
            "Lean into surreal escalation.",
            "Use unexpected contrasts that still connect to the transcript.",
            "Keep each option punchy and imageable.",
        ],
        negative_rules=[
            "Do not drift so far that the transcript evidence disappears.",
            "No random proper nouns unless present in the source.",
        ],
    ),
    "deadpan": HumorStyleProfile(
        name="deadpan",
        label="Deadpan",
        rules=[
            "Write with a flat, matter-of-fact voice.",
            "Make the joke land through contrast between tone and content.",
            "Keep phrasing natural and low-drama.",
        ],
        negative_rules=[
            "No hype language.",
            "No internet slang unless quoted from the transcript.",
        ],
    ),
    "brainrot_light": HumorStyleProfile(
        name="brainrot_light",
        label="Brainrot Light",
        rules=[
            "Use internet-native phrasing sparingly.",
            "Keep it playful and current without becoming unreadable.",
            "Favor punchy patterns that feel meme-aware.",
        ],
        negative_rules=[
            "Avoid unreadable spammy slang.",
            "Do not use more than one slangy phrase per line.",
        ],
    ),
    "wholesome_ironic": HumorStyleProfile(
        name="wholesome_ironic",
        label="Wholesome Ironic",
        rules=[
            "Keep it warm and lightly self-aware.",
            "Balance sincerity with a wink.",
            "Prefer affectionate observations over roasting.",
        ],
        negative_rules=[
            "No cruelty.",
            "No edgy or mean-spirited framing.",
        ],
    ),
}


PRESET_REGISTRY: Dict[str, AnalysisPreset] = {
    "caption_ideas": AnalysisPreset(
        name="caption_ideas",
        label="Caption Ideas",
        output_label="caption",
        instructions=(
            "Generate social caption ideas for short-form content. Favor concise lines that could sit "
            "under a meme clip, reaction clip, or short edit."
        ),
        count=12,
    ),
    "hook_rewrites": AnalysisPreset(
        name="hook_rewrites",
        label="Hook Rewrites",
        output_label="hook",
        instructions=(
            "Rewrite the core moment into better opening hooks for short-form content. Front-load curiosity, "
            "conflict, or absurdity while staying faithful to the transcript."
        ),
        count=10,
    ),
    "title_pack": AnalysisPreset(
        name="title_pack",
        label="Title Pack",
        output_label="title",
        instructions=(
            "Create platform-friendly title ideas for social clips and short videos. Make them clickable "
            "without becoming misleading."
        ),
        count=10,
    ),
    "custom_prompt": AnalysisPreset(
        name="custom_prompt",
        label="Custom Prompt",
        output_label="response",
        instructions=(
            "Run a user-provided transcript analysis prompt and return a grounded answer."
        ),
        count=1,
    ),
}


class OllamaAnalyzer:
    def __init__(self, model: str = DEFAULT_ANALYSIS_MODEL):
        self.model = model
        self.client = ollama.Client()
        self.keep_alive = "0s"

    @staticmethod
    def _normalize_model_name(name: str) -> str:
        return name.strip().lower().split(":")[0]

    @staticmethod
    def _extract_model_names(response: Any) -> List[str]:
        names: List[str] = []

        if isinstance(response, dict):
            for model in response.get("models", []):
                name = model.get("name") or model.get("model")
                if name:
                    names.append(str(name))
            return names

        model_list = getattr(response, "models", None)
        if model_list:
            for model in model_list:
                name = getattr(model, "model", None) or getattr(model, "name", None)
                if name:
                    names.append(str(name))
        return names

    @staticmethod
    def _extract_chat_content(response: Any) -> str:
        if isinstance(response, dict):
            return response.get("message", {}).get("content", "")

        message = getattr(response, "message", None)
        if message is not None:
            content = getattr(message, "content", "")
            if content:
                return str(content)
        return ""

    @staticmethod
    def get_presets() -> List[Dict[str, str]]:
        return [
            {"name": preset.name, "label": preset.label, "output_label": preset.output_label}
            for preset in PRESET_REGISTRY.values()
        ]

    @staticmethod
    def get_humor_styles() -> List[Dict[str, str]]:
        return [
            {"name": style.name, "label": style.label}
            for style in HUMOR_STYLE_REGISTRY.values()
        ]

    @staticmethod
    def _clamp_transcript(transcript: str, limit: int = MAX_SOURCE_CHARS) -> str:
        normalized = transcript.strip()
        return normalized[:limit]

    @staticmethod
    def _safe_json_loads(payload: str) -> Any:
        cleaned = payload.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(1))

    async def list_available_models(self) -> List[str]:
        try:
            models = await asyncio.to_thread(self.client.list)
            return self._extract_model_names(models)
        except Exception:
            return []

    async def check_model_availability(self) -> bool:
        try:
            requested = self._normalize_model_name(self.model)
            available_models = await self.list_available_models()
            if not available_models:
                return False

            for name in available_models:
                normalized = self._normalize_model_name(name)
                if normalized == requested or name.lower() == self.model.lower():
                    return True
            return False
        except Exception:
            return False

    async def resolve_model_name(self) -> Optional[str]:
        requested = self._normalize_model_name(self.model)
        for name in await self.list_available_models():
            if self._normalize_model_name(name) == requested or name.lower() == self.model.lower():
                return name
        return None

    async def ensure_model(self) -> bool:
        resolved = await self.resolve_model_name()
        if resolved:
            self.model = resolved
            return True

        try:
            await asyncio.to_thread(self.client.pull, self.model)
            resolved = await self.resolve_model_name()
            if resolved:
                self.model = resolved
                return True
            return False
        except Exception as e:
            print(f"Failed to pull model {self.model}: {e}")
            return False

    async def _generate_response(self, prompt: str, system_prompt: str = "") -> str:
        try:
            response = await asyncio.to_thread(
                self.client.chat,
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                keep_alive=self.keep_alive,
            )
            content = self._extract_chat_content(response)
            return content or "Error: Empty model response"
        except Exception as e:
            return f"Error: {str(e)}"

    async def summarize(self, transcript: str) -> str:
        system_prompt = (
            "You produce concise grounded summaries from transcripts. Stick to source evidence."
        )
        prompt = f"""
Create a compelling summary of this transcript. Focus on the main themes, key insights, and most interesting points.
Keep it engaging and informative, around 3-5 sentences.

Transcript:
{self._clamp_transcript(transcript, 5000)}
"""
        return await self._generate_response(prompt, system_prompt)

    async def extract_quotes(self, transcript: str, max_quotes: int = 10) -> List[str]:
        system_prompt = "You extract grounded notable quotes from transcripts."
        prompt = f"""
Find up to {max_quotes} quotable moments from this transcript.
Return ONLY a JSON array of strings. Use exact or near-exact wording grounded in the transcript.

Transcript:
{self._clamp_transcript(transcript, 5000)}
"""
        response = await self._generate_response(prompt, system_prompt)

        try:
            quotes = self._safe_json_loads(response)
            return [str(quote).strip() for quote in quotes if str(quote).strip()][:max_quotes]
        except Exception:
            lines = response.split("\n")
            quotes = []
            for line in lines:
                cleaned = re.sub(r'^[-*•\d\.\)\s"]+', "", line).strip().strip('"\'')
                if len(cleaned) > 20:
                    quotes.append(cleaned)
            return quotes[:max_quotes]

    async def extract_topics(self, transcript: str) -> List[str]:
        system_prompt = "You identify grounded transcript themes."
        prompt = f"""
Identify the main topics and themes in this transcript.
Return ONLY a JSON array of 5-10 strings.

Transcript:
{self._clamp_transcript(transcript, 5000)}
"""
        response = await self._generate_response(prompt, system_prompt)

        try:
            topics = self._safe_json_loads(response)
            return [str(topic).strip() for topic in topics if str(topic).strip()][:10]
        except Exception:
            lines = response.split("\n")
            topics = []
            for line in lines:
                cleaned = re.sub(r"^[-*•\d\.\)\s]+", "", line).strip()
                if cleaned:
                    topics.append(cleaned)
            return topics[:10]

    async def analyze_sentiment(self, transcript: str) -> str:
        system_prompt = "You analyze the overall emotional tone of transcripts."
        prompt = f"""
Analyze the overall sentiment and emotional tone of this transcript.
Describe it in 1-2 sentences, focusing on the dominant emotions and overall vibe.

Transcript:
{self._clamp_transcript(transcript, 5000)}
"""
        return await self._generate_response(prompt, system_prompt)

    async def custom_analysis(self, transcript: str, custom_prompt: str) -> str:
        prompt = (
            f"{custom_prompt}\n\n"
            "Use the following transcript as source material. "
            "If evidence is not present, say so explicitly.\n\n"
            f"Transcript:\n{self._clamp_transcript(transcript)}"
        )
        return await self._generate_response(prompt)

    async def build_digest(self, transcript: str) -> str:
        system_prompt = (
            "You are a transcript strategist. Extract only grounded evidence from the transcript for downstream "
            "creative rewriting. Be concise and structured."
        )
        prompt = f"""
Analyze this transcript and return ONLY JSON with this shape:
{{
  "beats": ["short beat", "..."],
  "tone": ["tone tag", "..."],
  "quotable_moments": ["short quote or paraphrase", "..."],
  "meme_angles": ["grounded angle", "..."],
  "safety_notes": ["risk note", "..."]
}}

Rules:
- Stay grounded in the transcript.
- Do not invent people, events, or context.
- Keep each string short.
- Return valid JSON only.

Transcript:
{self._clamp_transcript(transcript, MAX_DIGEST_CHARS)}
"""
        response = await self._generate_response(prompt, system_prompt)
        try:
            payload = self._safe_json_loads(response)
            return json.dumps(payload, ensure_ascii=False, indent=2)
        except Exception:
            fallback = {
                "beats": [],
                "tone": [],
                "quotable_moments": [],
                "meme_angles": [],
                "safety_notes": ["Digest parsing failed; downstream generation should stay conservative."],
            }
            return json.dumps(fallback, ensure_ascii=False, indent=2)

    async def run_preset(
        self,
        transcript: str,
        preset_name: str = DEFAULT_PRESET,
        humor_style: str = DEFAULT_HUMOR_STYLE,
        custom_prompt: str = "",
    ) -> PresetResult:
        transcript = transcript.strip()
        if not transcript:
            raise ValueError("Transcript is required for analysis.")

        if not await self.ensure_model():
            raise RuntimeError(f"Model {self.model} is not available and could not be downloaded")

        preset = PRESET_REGISTRY.get(preset_name)
        if not preset:
            raise ValueError(f"Unsupported preset: {preset_name}")

        style = HUMOR_STYLE_REGISTRY.get(humor_style)
        if not style:
            raise ValueError(f"Unsupported humor style: {humor_style}")

        if preset_name == "custom_prompt":
            prompt = custom_prompt.strip()
            if not prompt:
                raise ValueError("Custom prompt is required.")

            digest = await self.build_digest(transcript)
            content = await self.custom_analysis(
                transcript,
                (
                    f"{prompt}\n\n"
                    "Use the digest as additional context, but stay grounded in the transcript.\n\n"
                    f"Digest:\n{digest}"
                ),
            )
            return PresetResult(
                preset=preset.name,
                humor_style=style.name,
                model=self.model,
                digest=digest,
                items=[],
                custom_prompt=prompt,
                custom_response=content.strip(),
                raw_output=content,
            )

        digest = await self.build_digest(transcript)
        system_prompt = (
            "You generate structured social-media ideation based strictly on transcript evidence. "
            "Return valid JSON only."
        )
        prompt = f"""
You are generating a `{preset.name}` pack.

Preset goal:
{preset.instructions}

Humor style:
{style.as_prompt_block()}

Return ONLY valid JSON with this shape:
{{
  "items": [
    {{
      "{preset.output_label}": "text",
      "humor_style": "{style.name}",
      "score": 0.0,
      "why_it_works": "short rationale",
      "risk_flags": ["flag"]
    }}
  ]
}}

Rules:
- Generate exactly {preset.count} items.
- Scores must be between 0 and 1.
- Keep every item grounded in the transcript and digest.
- Use empty arrays for `risk_flags` when there are no concerns.
- If the transcript is thin, still provide options but note uncertainty in `why_it_works`.
- Do not output markdown or commentary.

Digest:
{digest}

Transcript excerpt:
{self._clamp_transcript(transcript)}
"""
        response = await self._generate_response(prompt, system_prompt)
        items = self._parse_preset_items(response, preset.output_label, style.name)

        return PresetResult(
            preset=preset.name,
            humor_style=style.name,
            model=self.model,
            digest=digest,
            items=items,
            raw_output=response,
        )

    def _parse_preset_items(
        self,
        response: str,
        output_label: str,
        humor_style: str,
    ) -> List[AnalysisItem]:
        try:
            payload = self._safe_json_loads(response)
        except Exception:
            payload = {"items": []}

        raw_items = payload.get("items", []) if isinstance(payload, dict) else []
        parsed_items: List[AnalysisItem] = []

        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue

            text = str(raw_item.get(output_label, "")).strip()
            if not text:
                continue

            risk_flags = raw_item.get("risk_flags", [])
            if not isinstance(risk_flags, list):
                risk_flags = [str(risk_flags)]

            try:
                score = float(raw_item.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0

            parsed_items.append(
                AnalysisItem(
                    text=text,
                    humor_style=str(raw_item.get("humor_style", humor_style)).strip() or humor_style,
                    score=max(0.0, min(score, 1.0)),
                    why_it_works=str(raw_item.get("why_it_works", "")).strip(),
                    risk_flags=[str(flag).strip() for flag in risk_flags if str(flag).strip()],
                )
            )

        if parsed_items:
            return parsed_items

        fallback_items: List[AnalysisItem] = []
        for line in response.splitlines():
            cleaned = re.sub(r"^[-*•\d\.\)\s]+", "", line).strip()
            if cleaned:
                fallback_items.append(
                    AnalysisItem(
                        text=cleaned,
                        humor_style=humor_style,
                        score=0.35,
                        why_it_works="Recovered from non-JSON model output.",
                        risk_flags=["unstructured_model_output"],
                    )
                )
        return fallback_items[:8]

    async def test_model_response(self) -> str:
        prompt = "Reply with exactly: MODEL_OK"
        return await self._generate_response(prompt, "You are a concise assistant.")

    async def full_analysis(self, transcript: str) -> AnalysisResult:
        if not await self.ensure_model():
            raise RuntimeError(f"Model {self.model} is not available and could not be downloaded")

        summary = await self.summarize(transcript)
        quotes = await self.extract_quotes(transcript)
        topics = await self.extract_topics(transcript)
        sentiment = await self.analyze_sentiment(transcript)
        caption_pack = await self.run_preset(transcript, "caption_ideas", DEFAULT_HUMOR_STYLE)

        return AnalysisResult(
            summary=summary,
            key_points=[],
            quotes=quotes,
            topics=topics,
            sentiment=sentiment,
            custom_analysis={"caption_ideas": caption_pack.to_dict()},
        )


async def test_analyzer() -> None:
    analyzer = OllamaAnalyzer()
    sample_transcript = """
    Welcome to today's podcast. We're talking about the future of artificial intelligence
    and how it's going to change everything. I think AI is going to be the most transformative
    technology of our lifetime. It's already changing how we work, how we create, and how we think.

    But there are also serious concerns. What happens to jobs? What about privacy?
    These are questions we need to answer now, not later.

    The key is to stay informed and stay engaged. Technology isn't destiny - we shape how it develops.
    """

    try:
        print("Running full analysis...")
        result = await analyzer.full_analysis(sample_transcript)
        print(f"\nSummary: {result.summary}")
        print(f"\nQuotes: {result.quotes}")
        print(f"\nTopics: {result.topics}")
        print(f"\nSentiment: {result.sentiment}")
    except Exception as e:
        print(f"Analysis failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_analyzer())
