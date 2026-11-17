# Requirements

- Survey item: "Do you feel Northeastern students have any advantages over non-Northeastern peers? Please explain?"
- Grounded answers only. Hard filter stays in front of any model. Do not fine-tune. Do not send every row to a generative model.
- Race and gender stay off the UI and are not loaded into Record.
- Campus is unreliable before 2023.
- Server is 127.0.0.1:8787. Do not kill unrelated pid 65860 on 8765.
- Do not commit unless asked. Do not print API keys. .env is gitignored.
- A key saved in Library (data/model.json) overrides .env.
- App is stdlib Python only. UI is vanilla HTML/CSS/JS.
- Northeastern brand: black #000000, white #FFFFFF, red #C8102E under about 25%, canvas #F6F6F4, subtle #3A3A3A, border #D9D9D6. Lato. Sharp 2px corners. No shadows. SVG icons. 44px targets. Focus rings. prefers-reduced-motion.
- LLM settings names: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL. UI labels: LLM key, Endpoint, LLM name. Dash base https://api-llm.dashlab.studio/v1, model gemma4:31b (the host does not serve gemma4:latest), think false.
- Each answer shows Scope, Stance, Reasons, and Evidence, then one summary paragraph. Quotations stay beside the paragraph. Accuracy panel checks numbers, quotations, and the refusal line.
- Insufficient support hides the reason ranking. Fallback paragraph is the grounded headline when the LLM fails.
- A count, comparison, or reason-ranking question also shows a small chart or table from those counts. A question the comments cannot answer, or a slice with insufficient support, has no chart.
- The opening screen lists nine sample questions in three groups: Bar chart, Table, and No chart.
- Ask one slice at a time. Parser colleges: Khoury / computer science / ccis, engineering, business school / damore / mckim (not the word business alone), Bouve, college of science, cssh / social sciences, camd / arts media, cps / professional studies, law school / law students. Levels: undergraduate, graduate, law. Years 2016–2026. Period compare needs the word changed and a year.
