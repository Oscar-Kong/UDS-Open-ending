# UDS open-ended prototype

A local viewer for one Northeastern graduate survey item:

> Do you feel Northeastern students have any advantages over non-Northeastern peers? Please explain.

The proposal asks for a chatbot that answers from these comments, shows quotations, and says when the evidence is not enough. This app is that chat, plus a library tab for the CSV and an evaluation tab for model scores. Answers use the hard-filtered comments. Without an LLM key, every answer is the filtered counts and quotations. With a key, the model writes only the short summary. The current endpoint is Dash at `https://api-llm.dashlab.studio/v1`, model `gemma4:31b`. The chat box lists model names from `GET /models` on that host. A key saved in Library overrides `.env`.

## Setup

You need Python 3.10 or newer. There is no `pip install`. The app uses the Python standard library, and the survey file `UDS_Cleaned.csv` is already in the repo. Race and gender are not in the chat.

Clone the repo and start the server from the project folder:

```bash
git clone https://github.com/Oscar-Kong/UDS-Open-ending.git
cd UDS-Open-ending
python3 app.py
```

Open http://127.0.0.1:8787. Leave that terminal running. Stop the server with Ctrl-C.

The first screen works with no key. To let a model write the summary, create a file named `.env` in the project folder (it stays on your machine and is not committed):

```
LLM_API_KEY=paste-the-key-here
LLM_BASE_URL=https://api-llm.dashlab.studio/v1
LLM_MODEL=gemma4:31b
```

`DASH_API_KEY` is accepted in place of `LLM_API_KEY`. Restart `python3 app.py` after you edit `.env`. You can also paste the key, endpoint, and model name in the Library tab. A key saved there overrides `.env`. Chats, evaluation runs, and an imported CSV are written under `data/` on this machine and are not committed.

To check the filter and the six scored questions without starting the server:

```bash
python3 pipeline/hard_filter.py
python3 pipeline/check_accuracy.py
```

## Using the app

The interface follows Northeastern’s black, white, and red brand, set in Lato. The opening screen greets Northeastern faculty by time of day, then lists sample questions grouped by whether the answer shows a bar chart, a comparison table, or no chart.

The Model menu in the chat box chooses which model writes the next summary. The names come from the endpoint. If that list does not load, the menu keeps the last list saved on this machine, and for Dash it keeps `gemma4:31b`, `nemotron3:33b`, and `qwen3.8:27b`. The sidebar stays in place while an answer scrolls, and only the history list scrolls when the list is long. Scope, stance, and reasons sit in a narrow table on the left as soon as a question is asked, and the summary fills the remaining width beside it. A new answer appears a few words at a time. People who prefer reduced motion see the full answer at once. The sidebar keeps the conversation. After the first answer is saved, the model writes a short title for that chat, the way a chat app names a thread. If the model does not answer, the call is tried once more, and the title stays the question. The same one retry applies to the answer itself. New chat starts a fresh thread and leaves the previous one in History. Delete removes that record. Chats are stored in `data/chats.json` on this machine (the 50 most recent).

## Evaluation

The Evaluation tab scores models on the same six questions as `python3 pipeline/check_accuracy.py`. The record follows [Inspect](https://inspect.aisi.org.uk/eval-logs.html), the open-source evaluation log from the UK AI Security Institute: one dataset, one solver, and scorers that mark each sample correct (`C`) or incorrect (`I`).

| Inspect piece | In this app |
| --- | --- |
| Dataset | The six questions in `pipeline/check_accuracy.py` |
| Solver | `pipeline.chat.reply` |
| Scorers | Numbers, quotations, and the refusal line |
| Eval log | `data/evals.json` |

Filtered counts can sit in the same table as one or more models, so every result uses the same questions and the same checks. A model is called once per question. A call that fails is scored incorrect. Up to four models can run together, and the twenty most recent runs are kept. Click a Pass or Fail cell to read the paragraph and the three checks.

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
