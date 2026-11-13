# AgentFoundry feedback (v0.1.80, Windows 11)

## Eval "Run" buttons fail on Windows: backslashes stripped from the suite path

**What happens.** In the Agents panel → Evals, pressing **Run** next to a suite (or **Run all**) fails with:

```
Eval failed: Could not read suite: ENOENT: no such file or directory, open
'C:\Users\<user>\AppData\Local\Programs\codenow\Users<user>Desktop...agentfoundry.codenowagent-studioevalskhidki-planner.json'
```

Every backslash of the project path is gone, so the path becomes relative to the install folder.

**Why.** `resources/app/src/renderer/app.js` builds the button as

```js
onclick="studioRunEvalFile('${escHtml(e.file)}')"
```

`escHtml` makes the value safe for HTML but not for a JavaScript string literal. A Windows path such as `C:\Users\me\...` reaches the inline handler as a JS string, where `\U`, `\m`, `\D` … are read as escape sequences and the backslashes disappear.

**Fix.** Put the path in a data attribute and read it in the handler, e.g.

```js
`<button data-file="${escHtml(e.file)}" class="eval-run">Run</button>`
// …
el.querySelectorAll('.eval-run').forEach(b => b.addEventListener('click', () => studioRunEvalFile(b.dataset.file)));
```

or emit the literal with `JSON.stringify(e.file)` (then HTML-escape it). The same pattern is worth checking in other inline `onclick` handlers that receive file paths.

**Repro.** Windows, any project under `C:\Users\...` with a suite in `.codenow/agent-studio/evals/`, press Run.

## AgentCert needs a TrustModel key, and TrustModel sign-up rejects common email domains

Registering at app.trustmodel.ai with several personal addresses returned "This email is not allowed, Please try other email". Without a Starter key the TrustScore / AgentCert steps cannot run, so independent builders who do not have a company email cannot certify their agents. A sign-in through AgentFoundry's own account, or allowing personal domains for the free Starter tier, would remove that wall.
