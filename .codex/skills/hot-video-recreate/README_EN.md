<h1 align="center">
  <strong>hot-video-recreate</strong>
</h1>

<p align="center">
  <strong>English</strong>
  &nbsp;·&nbsp;
  <a href="README.md"><strong>简体中文</strong></a>
</p>

<p align="center">
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/version-v1.0.0-orange" alt="Version"></a>
  &nbsp;
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
</p>

<p align="center">
  Viral video recreation + intelligent model routing.<br>
  One command: reference video + product image → your video, with the viral DNA preserved but never cloned.
</p>

---

## 🎯 What it does

**hot-video-recreate** solves two hard problems in AI video production:

### 1. Viral Video Recreation

Every viral video on any platform is a bundle of validated signals — storyboard rhythm, camera movement, transition patterns, pacing. Copy it directly and you get homogenization. Ignore it and you leave money on the table.

hot-video-recreate extracts the **structural DNA** of a reference viral video (shot composition, rhythm, motion grammar, transition logic) and migrates it to your product or brand — keeping what made the original work while making the output unmistakably yours.

> **The logic**: Viral elements on video platforms are market-validated. Direct copying triggers homogenization penalties. hot-video-recreate preserves the viral skeleton while dressing it in your domain's skin — cross-category migration without the sameness problem.

**Who it's for**: E-commerce sellers, new media creators, brand marketers — anyone who needs to turn a product into a video that works, without starting from scratch every time.

### 2. Intelligent Model Routing

Not every shot needs the most expensive model. Seedance, Kling, Wanxiang, VEO, Sora — each has a sweet spot. Some excel at realistic humans, others at product close-ups, others at text-heavy overlays. Throwing everything at the flagship model burns budget for no reason.

hot-video-recreate's **router** understands each model's boundaries and assigns every segment to the model that delivers the required quality at the lowest cost. Currently supports multiple Seedance versions with same-quality cost reduction. More models (Kling, Wanxiang, VEO, etc.) are being added to the routing table.

> **The logic**: Every model has its own value curve. Routing all tasks to the strongest model works — but it wastes compute and burns money. The router matches task profiles to model strengths, squeezing maximum quality from minimum cost.

**Current routing capability**: Seedance versions (doubao-seedance-2-0-fast, doubao-seedance-1-5-pro, etc.) — same visual quality, different price points.  
**Coming soon**: Kling, Wanxiang, VEO, Sora, and other video generation models.

**Cost**: As low as ¥0.4/second using official APIs, without sacrificing visual quality.

---

## ⚖️ How it differs from "prompt-to-video" tools

| Prompt-to-video tools | hot-video-recreate |
|---|---|
| You describe what you want in text | You show a reference video — it understands **how** it works |
| One model for everything | Smart routing across models by task profile |
| You guess what makes a good video | Viral DNA is **extracted, not imagined** |
| Same output regardless of cost | Quality-matched routing — pay only for what each segment needs |
| Single-model dependency | Multi-model redundancy — never locked into one API |

In a sentence: prompt-to-video tools ask you to be the director. hot-video-recreate gives you a calibrated production pipeline.

---

## 🚀 Quick Start

```bash
# 1. Enter the skill directory
cd %USERPROFILE%\.codex\skills\hot-video-recreate

# 2. Set up environment
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

# 3. Edit .env with your API keys
#    DASHSCOPE_API_KEY=sk-...
#    VOLC_ARK_API_KEY=ark-...

# 4. Run
python main.py --video "path/to/reference.mp4" --image "path/to/product.jpg" --resolution 720P
```

### One-liner for Codex users

Just say: `$recreate --video "ref.mp4" --image "product.jpg"` and Codex handles the rest.

---

## 📋 Parameters

| Parameter | Required | Description |
|---|---|---|
| `--video` | Yes | Reference viral video (local path or URL) |
| `--image` | Yes (1+) | Product reference image(s) |
| `--face` | No | Real person photo (triggers pencil-style compliance) |
| `--seconds` | Conditional | Video duration in seconds (required if ffprobe fails) |
| `--resolution` | No | Default `720P`; options: `480P` / `720P` / `1080P` / `4K` |
| `--product-name` | No | Product name |
| `--product-info` | No | Product description |
| `--skip-generate` | No | Generate compile JSON only, skip video rendering |

---

## 🧬 The Pipeline

```text
Reference Video + Product Image
        ↓
   [Normalize] — format inputs, detect duration
        ↓
   [Face Check] — optional pencil-style compliance for real faces
        ↓
   [Deconstruct] — extract viral DNA: shot composition, rhythm, transitions
        ↓
   [Adapt] — migrate DNA to target product/domain
        ↓
   [Compile] — generate per-segment generation prompts
        ↓
   [Route] — match each segment to optimal model (cost x quality)
        ↓
   [Generate] — render segments via Seedance / Kling / Wanxiang / VEO
        ↓
   outputs/<run_id>/segments/*.mp4
```

---

## 🧠 Why This Works

**For viral recreation**: Viral videos on any platform represent patterns that the platform's algorithm and audience have already validated. The structural elements (shot length distribution, motion intensity curve, transition density) are statistical signals, not creative accidents. Transferring these signals to a new domain preserves what worked while the domain shift naturally prevents homogenization.

**For model routing**: Video generation models have non-overlapping strength profiles. A model that excels at photorealistic human faces may be overkill for a product close-up with text overlay. A model tuned for fast turnaround may be perfect for B-roll but wrong for hero shots. The router learns these boundaries and allocates tasks accordingly — the same logic that makes CDNs cheaper than origin servers for static assets.

---

## 📦 Output Structure

```text
outputs/<run_id>/
├── manifest.json        # Generation metadata, status, model per segment
├── dna.json             # Extracted viral DNA
├── adapted.json         # Domain-adapted script
├── compile.json         # Per-segment generation prompts with routing decisions
└── segments/
    ├── 001.mp4
    ├── 002.mp4
    └── ...
```

---

## 🔑 Supported Models

| Model | Status | Best For |
|---|---|---|
| Seedance 2.0 Mini | Routing | Lightweight fast generation |
| Seedance 2.0 Fast | Routing | Fast turnaround, product shots |
| Seedance 2.0 | Routing | Standard quality, general purpose |
| Kling | Coming | Realistic human motion |
| Wanxiang | Coming | Cinematic quality |
| VEO | Coming | Text-to-video fidelity |
| Sora | Coming | Scene consistency |
| Grok | Coming | Real-time visual understanding |
| Gemini-Omni | Coming | Multimodal-native generation |

---

## 📐 Requirements

- Python 3.10+
- `DASHSCOPE_API_KEY` (Alibaba Bailian — for deconstruct/adapt/compile)
- `VOLC_ARK_API_KEY` (Volcano Ark — for Seedance video generation)
- ffprobe (optional, auto-detected for video duration)

---

## 📄 License

MIT. Commercial use, modification, and closed-source integration — all fine.

**Attribution**: If you use this project, please credit the source and include a link back to this repository.

