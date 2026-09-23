"""Reference prompt and parser; model dependencies are loaded only for inference."""
import gc
import json

MODEL_ID = "Qwen/Qwen3.5-4B"

SEED = 42

PROMPT = """
Du erhältst ein oder mehrere Bilder derselben Zielperson.

WICHTIGE REGEL ZUR PERSONENIDENTITÄT:
- Analysiere ausschließlich die Zielperson des Personen-Crops.
- Andere Personen, die zufällig im Hintergrund, am Bildrand oder teilweise im Personen-Crop sichtbar sind, müssen ignoriert werden.
- Bei mehreren Bildern gehört die wiederholt sichtbare Zielperson immer zur selben Identität.
- Vermische niemals Merkmale verschiedener Personen.

ALLGEMEINE REGELN:
- Nutze alle bereitgestellten Bilder gemeinsam.
- Ein Merkmal darf aus einem Bild übernommen werden, wenn es dort zuverlässig sichtbar ist, auch wenn es in anderen Bildern verdeckt oder nicht sichtbar ist.
- Bei widersprüchlichen oder unsicheren Informationen verwende "nicht erkennbar".
- Nutze keine Informationen, die nicht direkt aus den Bildern hervorgehen.
- Rate nicht.
- Gib ausschließlich ein gültiges JSON-Objekt aus, ohne Erklärung oder Markdown.

FARBEN:
- Bestimme Farben nur anhand von Bildern, in denen natürliche und zuverlässige Farben erkennbar sind.
- Verwende keine Farbinformationen aus Schwarz-Weiß-, Sepia-, monochrom eingefärbten oder stark farbstichigen Bildern.
- Ein Bild ist für die Farbbestimmung ungeeignet, wenn große Teile des gesamten Bildes durchgehend denselben unnatürlichen Farbton haben, zum Beispiel deutlich blau, grün, gelb, rot oder braun eingefärbt wirken.
- Leite aus einem solchen allgemeinen Farbstich niemals die Farbe von Haaren, Kopfbedeckung oder Kleidung ab.
- Wenn zusätzlich Bilder mit natürlichen und zuverlässigen Farben vorhanden sind, nutze nur diese für die Farbbestimmung.
- Wenn für ein Farbattribut keine zuverlässige Farbinformation vorhanden ist, verwende "nicht erkennbar".

HAARFARBE:
- Bewerte die Haarfarbe nur anhand tatsächlich sichtbarer Haare.
- Wenn Haare nur minimal sichtbar oder farblich unsicher sind, verwende "nicht erkennbar".

HAARLÄNGE:
- Bewerte die tatsächliche Haarlänge und nicht das Haarvolumen.
- Wenn die Haarlänge nicht zuverlässig sichtbar ist, verwende "nicht erkennbar".
- Verwende folgende Einteilung:
  - "glatze" = sichtbar haarloser oder nahezu haarloser Kopf
  - "sehr kurz" = sehr nah am Kopf, kaum sichtbare Haarlänge
  - "kurz" = reicht nicht deutlich über die Ohren beziehungsweise nur wenig in den Nacken
  - "mittellang" = reicht deutlich über die Ohren beziehungsweise in den Nacken und bis ungefähr zu den Schultern
  - "lang" = reicht sichtbar über die Schultern hinaus

KOPFBEDECKUNG:
- Wenn eindeutig keine Kopfbedeckung vorhanden ist, setze "headwear" auf "keine" und "headwear_color" auf "entfällt".
- Wenn die Kopfbedeckung nicht zuverlässig erkennbar ist, verwende "nicht erkennbar".

STATUR:
- Bewerte die Statur nur, wenn ausreichend viel vom Oberkörper beziehungsweise Rumpf sichtbar ist.
- Kopf, Gesicht, Hals oder Schultern allein reichen nicht aus.
- Wenn weite Kleidung, Verdeckung oder ein enger Bildausschnitt die Körperform nicht zuverlässig erkennen lassen, verwende "nicht erkennbar".
- "schlank" = deutlich schmale Körperform.
- "normal" = weder deutlich schlank noch deutlich kräftig.
- "kräftig" = deutlich breite beziehungsweise deutlich voluminöse Körperform.

KLEIDUNG:
- Bei "upper_clothing" und "lower_clothing" nur die Art des Kleidungsstücks nennen.
- Geeignete Begriffe sind zum Beispiel "T-Shirt", "Hemd", "Bluse", "Polo-Shirt", "Pullover", "Hoodie", "Top", "Cardigan", "Jacke", "Mantel", "Kleid", "Hose", "Jeans", "Shorts" oder "Rock".
- Farben ausschließlich in "upper_color" beziehungsweise "lower_color" eintragen.
- Ist ein Kleidungsstück nicht zuverlässig erkennbar, verwende "nicht erkennbar".
- Wenn eindeutig ein Kleid getragen wird, setze "upper_clothing" und "lower_clothing" auf "Kleid".
- Bei einem Kleid verwende für "upper_color" und "lower_color" dieselbe sichtbare Farbe des Kleides.

{
  "hair_color": "blond | braun | schwarz | grau | rot | andere | nicht erkennbar",
  "hair_length": "glatze | sehr kurz | kurz | mittellang | lang | nicht erkennbar",
  "headwear": "keine | Helm | Kappe | Hut | Mütze | andere | nicht erkennbar",
  "headwear_color": "Farbe | entfällt | nicht erkennbar",
  "beard": "ja | nein | nicht erkennbar",
  "glasses": "ja | nein | Sonnenbrille | nicht erkennbar",
  "age_group": "<=16 | 17-30 | 31-45 | 46-60 | >60 | nicht erkennbar",
  "body_build": "schlank | normal | kräftig | nicht erkennbar",
  "upper_clothing": "kurze konkrete Bezeichnung | nicht erkennbar",
  "upper_color": "Farbe | nicht erkennbar",
  "lower_clothing": "kurze konkrete Bezeichnung | nicht erkennbar",
  "lower_color": "Farbe | nicht erkennbar"
}
""".strip()

FIELDS = [
    "hair_color",
    "hair_length",
    "headwear",
    "headwear_color",
    "beard",
    "glasses",
    "age_group",
    "body_build",
    "upper_clothing",
    "upper_color",
    "lower_clothing",
    "lower_color",
]

LABELS = {
    "hair_color": "Haarfarbe",
    "hair_length": "Haarlänge",
    "headwear": "Kopfbedeckung",
    "headwear_color": "Farbe Kopfbedeckung",
    "beard": "Bart",
    "glasses": "Brille",
    "age_group": "Alter",
    "body_build": "Statur",
    "upper_clothing": "Oberbekleidung",
    "upper_color": "Farbe Oberbekleidung",
    "lower_clothing": "Unterbekleidung",
    "lower_color": "Farbe Unterbekleidung",
}

def parse_json(text: str) -> dict[str, str]:
    text = text.strip()

    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    elif text.startswith("```"):
        text = text[3:].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    decoder = json.JSONDecoder()
    candidates = []

    for index, char in enumerate(text):
        if char != "{":
            continue

        try:
            data, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict):
            candidates.append(data)

    if not candidates:
        raise ValueError("Kein vollständiges JSON gefunden")

    data = max(
        candidates,
        key=lambda item: sum(field in item for field in FIELDS),
    )

    if not any(field in data for field in FIELDS):
        raise ValueError("JSON gefunden, aber keine erwarteten Attribute")

    return {
        field: str(data.get(field, "")).strip()
        for field in FIELDS
    }

def build_messages(image_items: list[dict]) -> list[dict]:
    content = [
        {
            "type": "image",
            "path": str(item["image_path"]),
        }
        for item in image_items
    ]

    content.append(
        {
            "type": "text",
            "text": PROMPT,
        }
    )

    return [
        {
            "role": "user",
            "content": content,
        }
    ]

GENERATION = {
    'max_new_tokens': 512, 'do_sample': False, 'temperature': 0.7,
    'top_p': 0.8, 'top_k': 20, 'min_p': 0.0, 'repetition_penalty': 1.0,
}


class QwenAttributes:
    def __enter__(self):
        import torch
        from transformers import AutoProcessor, AutoModelForMultimodalLM
        self.torch = torch
        self.processor = self.model = None
        try:
            self.processor = AutoProcessor.from_pretrained(MODEL_ID)
            self.model = AutoModelForMultimodalLM.from_pretrained(MODEL_ID, device_map='auto')
            self.model.eval()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def predict(self, person_id, paths):
        from transformers import set_seed
        set_seed(SEED + person_id)
        inputs = outputs = None
        try:
            inputs = self.processor.apply_chat_template(
                build_messages([{'image_path': path} for path in paths]),
                add_generation_prompt=True, tokenize=True, return_dict=True,
                return_tensors='pt', enable_thinking=False,
            ).to(self.model.device)
            with self.torch.inference_mode():
                outputs = self.model.generate(**inputs, **GENERATION)
            return self.processor.decode(outputs[0][inputs['input_ids'].shape[-1]:], skip_special_tokens=True).strip()
        finally:
            del inputs, outputs

    def __exit__(self, *args):
        self.model = self.processor = None
        gc.collect()
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
