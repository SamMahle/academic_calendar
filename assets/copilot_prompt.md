# Copilot Handoff Prompt

Use this prompt when CadetCal cannot confidently extract events from a syllabus.
Open the syllabus in Microsoft 365 Copilot, paste this prompt, then paste the
resulting table back into CadetCal.

---

Extract every graded event from this syllabus into a table with the following
columns:

| Event Type | Event Name | Due Date (DD MMM YYYY) | Lesson Reference | Weight (%) |

Rules:
- **Event Type** must be one of: WPR, TEE, Writ, PS, HW, Quiz, Lab, Project, Other
- **Event Name** is a short label (e.g. "WPR 1", "PS #3", "Lab Report 2")
- **Due Date** format: DD MMM YYYY (e.g. 14 Feb 2026). Use "TBD" if not specified.
- **Lesson Reference** format: L## (e.g. L12) or blank if none given.
- **Weight (%)** is the percentage of the final grade. Use blank if not stated.
- Include only items that affect the final grade.
- Do NOT include administrative items (syllabus quiz, attendance, etc.) unless they are explicitly graded.

Output as a Markdown table with exactly these five columns. No extra commentary.
