# UDS open-ended prototype

A local viewer for one Northeastern graduate survey item:

> Do you feel Northeastern students have any advantages over non-Northeastern peers? Please explain.

The proposal asks for a chatbot that answers from these comments, shows quotations, and says when the evidence is not enough. This app is that chat, plus a library tab for the CSV. Answers use the hard-filtered comments. Paste an LLM key into `.env` as `LLM_API_KEY` (or `DASH_API_KEY`), with `LLM_BASE_URL` and `LLM_MODEL`, then restart the app, when you want an LLM to write the short summary. The current endpoint is Dash at `https://api-llm.dashlab.studio/v1`, model `gemma4:31b`. Model names come from `GET /models` on that host. A key saved in Library overrides `.env`.

## Run

```bash
python3 app.py
```

Open http://127.0.0.1:8787. The app uses the Python standard library and reads `UDS_Cleaned.csv`. Race and gender are not shown. The interface follows Northeastern’s black, white, and red brand, set in Lato. The opening screen lists sample questions grouped by whether the answer shows a bar chart, a comparison table, or no chart.

## What the hard filter does

| Bucket | Meaning | Later model use |
| --- | --- | --- |
| Set aside | Non-response (`n/a`, “no comment”) | Drop |
| Position only | Yes, no, or unsure, with no reason | Headcount only |
| Short reason | A label such as “co-op” or “yes, because of co-op” | Keyword tally only |
| Explanation | At least a short explanation | Embed, retrieve, quote |

Rules live in `pipeline/hard_filter.py` and are checked with `python3 pipeline/hard_filter.py`.

## Check an answer

Each answer starts with three counted passes — scope, stance, and reasons — and then one summary paragraph. The paragraph is written by the LLM from those figures only. When the LLM is unavailable, the paragraph is the filtered headline. A count, a comparison, or a reason ranking also shows a small chart or table from those same figures. A question the comments cannot answer stays as text, with no chart. An accuracy panel under the summary checks whether every number is in the filtered counts, whether each quotation matches an explanation, and whether a thin slice is refused. The same checks run in the terminal. `python3 pipeline/check_accuracy.py` checks six questions against the filtered file: the leading reason, the yes/no split, one comparison, one dissent theme, and two questions the item cannot answer.

Add `--llm` to score a live summary against that same packet. A number in the summary has to appear in the packet, a marked quotation has to be one of the packet quotations, and an insufficient slice has to be refused. To score one saved paragraph:

```bash
python3 pipeline/check_accuracy.py --question "What is the main reason students feel they have an advantage?" --text "Students name co-op in 8,909 explanations."
```

## Stages after this

1. Embed the explanation bucket with a small local model (`bge-small-en-v1.5` or MiniLM), after collapsing duplicate wording. Cluster, and split the co-op cluster.
2. Use a model to name clusters from sample quotations, then to write the Ask paragraph from the counts and quotations this screen already builds. If the slice is thin, the model has to say so.
3. Evaluate on a question list written with UDS. Check every quotation and every refusal.

Stance should stay a lexicon (plus a checker on the unlabeled explanations). Sentiment is the wrong label for this item. Do not send every row to a generative model. Full classification was left to the parallel team in the proposal; if those labels arrive, this screen should consume them.

The same outline is on the Stages tab in the app.
