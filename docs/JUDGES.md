# Review Khidki in five minutes

Nothing to install, no account, no keys.

## 1. Find a window (1 min)
Open **https://khidki-air.vercel.app/app**, pick a city (or "Use my location"), choose *Walk*, keep "usually at 06:00", press the button. You get the cleanest hour inside your limits, how much less PM2.5 than 06:00, the day as 24 cells (measured hours solid, forecast hatched), and the government monitors it used. Try *Children's play* (school hours) or set "Done by 10:00" to see Khidki say plainly that winter mornings have no clean slot.

## 2. Ask it in your language (1 min)
On Telegram open **https://t.me/Khidkitgbot**, press Start, share a location (or type an area), then write e.g. "kal subah 6 baje 1 ghanta walk karta hoon, office 9:30 ka hai". The reply names the time, the monitors and the confidence; every number in it comes from the engine. The same assistant is in the web app ("Ask Khidki").

## 3. Check that it was published before the day (2 min)
Open **https://khidki-air.vercel.app/ledger**. Each day lists the SHA-256 of everything Khidki recommended for every monitor, published at 21:00 IST the evening before.
- Press **Verify in your browser**: the page downloads the exact document and hashes it locally.
- Download the **.ots** proof and the JSON, then drop both on https://opentimestamps.org (or run `ots verify`) to see the Bitcoin timestamp.
- The scoreboard grades every recommendation against measured readings: Khidki's hour vs the usual time, a fixed 15:00 rule and the best hour in hindsight. Misses stay in.

## 4. See the monitors being checked (1 min)
Open **https://khidki-air.vercel.app/monitors**: every day, every active monitor is checked for silent hours, frozen values and silence while neighbours read Severe, with a bulletin in English and Hindi.

## Raw API
- `https://khidki-engine-ptslyhnp7q-el.a.run.app/docs` — every endpoint
- `/v1/window?lat=28.59&lon=77.22&activity=walk&minutes=60&habitual=06:00&day=tomorrow`
- `/v1/ledger`, `/v1/ledger/<day>.json`, `/v1/ledger/<day>.ots`, `/v1/scoreboard`, `/v1/audit`, `/v1/bulletin`, `/v1/impact`
- MCP (streamable HTTP): `https://khidki-engine-ptslyhnp7q-el.a.run.app/mcp/`

## Reproduce the numbers
See [CLAIMS.md](CLAIMS.md): every figure, its evidence tier and the script that recomputes it. The method, formulas and limits are in [METHOD.md](METHOD.md).
