# B2B Outreach Intelligence: Copywriting & Intent Guidelines

## 1. Zero AI Slop & Negative Copy Constraints
The system strictly enforces the following negative constraints on all generated drafts:
- **No Sycophantic Clichés:** Never use "I hope this email finds you well", "hope all is well", "game-changer", "synergy", "seamlessly", "dive into", "cutting-edge".
- **No Em-Dashes or Hyphen Overuse:** Never use em-dashes (`—`) or multiple parenthetical sidebars.
- **No Exclamation Marks:** Maintain a calm, peer-to-peer business tone.
- **No Invented Metrics:** Never claim fake percentages (e.g., "increase revenue by 32%"). Only cite facts verified in the prospect's dossier.
- **Low-Friction CTAs:** Never ask for a 30-minute phone call. Use low-friction asks: "Worth a look?", "Would you like me to send a 2-minute video overview?", or "Simply reply to let me know."

---

## 2. Channel Copy Length Limits
- **Cold Email:** Under 120 words total. Plain-text, 3-4 short paragraphs maximum.
- **WhatsApp Message:** Under 50 words. Ultra-short, casual, localized.
- **LinkedIn Connection Note:** Under 300 characters.
- **LinkedIn InMail / Message:** Under 600 characters.

---

## 3. Reply Intent Classification Categories
When polling Gmail or receiving incoming responses, replies are categorized into:
- `INTERESTED (Hot Lead)`: Prospect agreed to see a demo, asked for a link, or expressed interest.
  - *Action:* Updates contact to `HOT_LEAD`, flags for immediate human follow-up, triggers webhook alert.
- `PRICE_QUESTION`: Prospect asked about cost, packages, or pricing terms.
  - *Action:* Updates contact to `REPLIED`, alerts team to send pricing sheet.
- `NOT_NOW`: Prospect requested follow-up at a later date (e.g. "reach out next quarter").
  - *Action:* Updates contact to `FOLLOW_UP_LATER`, schedules delayed touchpoint.
- `UNSUBSCRIBE`: Prospect asked to be removed or expressed disinterest.
  - *Action:* Updates contact to `OPTED_OUT`, inserts email into `suppression_list` table permanently.
