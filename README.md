# UDS open-ended prototype

A local viewer for one Northeastern graduate survey item:

> Do you feel Northeastern students have any advantages over non-Northeastern peers? Please explain.

The proposal asks for a chatbot that answers from these comments, shows quotations, and says when the evidence is not enough. This app is that chat, plus a library tab for the CSV. Answers use the hard-filtered comments. Paste an OpenAI-compatible API key in Library when you want the model to write the short summary.

## Run

```bash
python3 app.py
```

Open http://127.0.0.1:8787. The app uses the Python standard library and reads `UDS_Cleaned.csv`. Race and gender are not shown. The interface follows Northeastern’s black, white, and red brand, set in Lato.

## What the hard filter does

| Bucket | Meaning | Later model use |
| --- | --- | --- |
| Set aside | Non-response (`n/a`, “no comment”) | Drop |
| Position only | Yes, no, or unsure, with no reason | Headcount only |
| Short reason | A label such as “co-op” or “yes, because of co-op” | Keyword tally only |
| Explanation | At least a short explanation | Embed, retrieve, quote |

Rules live in `pipeline/hard_filter.py` and are checked with `python3 pipeline/hard_filter.py`.

## Stages after this

1. Embed the explanation bucket with a small local model (`bge-small-en-v1.5` or MiniLM), after collapsing duplicate wording. Cluster, and split the co-op cluster.
2. Use a model to name clusters from sample quotations, then to write the Ask paragraph from the counts and quotations this screen already builds. If the slice is thin, the model has to say so.
3. Evaluate on a question list written with UDS. Check every quotation and every refusal.

Stance should stay a lexicon (plus a checker on the unlabeled explanations). Sentiment is the wrong label for this item. Do not send every row to a generative model. Full classification was left to the parallel team in the proposal; if those labels arrive, this screen should consume them.

The same outline is on the Stages tab in the app.
