# Contact form and Brevo

A website cannot send email by itself. It hands the message to a mail service, which
sends it on. This uses Brevo — free for the volume a contact form generates, and it
does not require touching the domain's existing mail setup at all.

**Adding a contact form does not change where the company's email goes.** Say this
early. It is the first thing a cautious person worries about, and the answer is a clean
no: the form sends *through* Brevo, using Brevo's own sending domain. The `MX` records
that deliver mail to staff are untouched.

## Walking them through Brevo

They do this in the browser. Give the click path.

> **1. Make an account**
> Go to **brevo.com** and sign up. The free plan is enough — a contact form sends a
> handful of messages a day, and the free allowance is 300.
>
> **2. Register the "from" address**
> Left menu → **Senders, Domains & Dedicated IPs** → **Senders** → **Add a sender**.
> Enter the address the form should send from — the one you told me earlier. Brevo
> emails that address a confirmation link; click it.
>
> **3. Get the key**
> Top-right account menu → **SMTP & API** → **API Keys** → **Generate a new API key**.
> Name it after the site. Copy it — it is only shown once.

Then take the key without seeing it:

```bash
npx wrangler pages secret put BREVO_API_KEY --project-name=<project>
```

It prompts, and does not echo. Ask them to paste it there. Do not ask them to paste the
key into the chat, do not put it in a file, and do not read it back to them.

## The trap that catches everyone

**The "from" address must be registered under Brevo → Senders. Verifying the domain is
not enough on its own.**

If the address is not registered, Brevo accepts the API call and returns success, then
blocks the send. The website reports "message sent". Nothing ever arrives. There is no
error anywhere the site can see.

So when a test message does not turn up, check sender registration *first*, before
suspecting the code, the key, spam filters, or DNS. This has been the cause every time.

Step 2 above is not optional and is not the same as step 1.

## Wiring it up

Copy `assets/contact.js.template` to `web/functions/api/contact.js` and substitute the
placeholders listed at the top of the file.

That path is not arbitrary. Cloudflare Pages serves everything in the built `dist/`
folder as static files and routes `/api/*` to whatever it finds in `functions/` next to
it. That is how the site stays a plain static build with no server framework — the form
is the only dynamic piece, and it lives outside the site build entirely.

The form in the page posts to `/api/contact`:

```html
<form class="contact-form" method="post" action="/api/contact">
  <!-- Honeypot: bots fill this in, humans never see it -->
  <div style="position:absolute; left:-9999px;" aria-hidden="true">
    <label>Leave this empty
      <input type="text" name="website" tabindex="-1" autocomplete="off" />
    </label>
  </div>
  <input type="text"  name="name"    maxlength="120"  required />
  <input type="email" name="email"   maxlength="255"  required />
  <input type="text"  name="subject" maxlength="200" />
  <textarea name="message" rows="5"  maxlength="5000" required></textarea>
  <button type="submit">Send</button>
  <p class="form-status" role="status" aria-live="polite" hidden></p>
</form>
```

Keep the `maxlength` values identical to the `LIMITS` in the function. If they drift,
the browser accepts something the server then rejects, and the visitor gets a failure
with no explanation.

Set `action` to `/api/contact`, never to `/`. A form posting to `/` on Pages hits a
static file, which answers `405 Method Not Allowed` — a real bug that reached
production once and looks, to a visitor, like the site is broken.

## How the handler behaves

Worth knowing, because these all look like bugs and are not:

| Situation | Response | Why |
|---|---|---|
| Honeypot filled | `200 {ok:true}`, nothing sent | Reporting failure teaches the bot to try again |
| Missing or bad field | `422 invalid` | — |
| Unparseable body | `400 bad_request` | — |
| `BREVO_API_KEY` not set | `500 unconfigured` | Fails loudly rather than pretending |
| Brevo refuses or is unreachable | `502 send_failed` | Brevo's reply is logged, never returned — it can contain account details |
| Anything but POST | `405` with `Allow: POST` | Answered explicitly, not left to the file server |

It works without JavaScript. A plain form submission gets a redirect back to the page it
came from with `?sent=1` or `?sent=0`; the page reads that on load and shows the message.
When JavaScript is on, a `fetch` gets JSON instead and the page never reloads. Both
paths must keep working — the no-JS path is the fallback when anything else breaks.

The email sets `replyTo` to whoever filled in the form, so hitting Reply in a mail
client goes to them rather than to the website.

## Testing

Merge to production first — **a preview deployment cannot send mail**, because secrets
are bound to production only. Then submit the form and check the receiving inbox,
including spam.

If nothing arrives, in this order:

1. **Is the "from" address registered under Brevo → Senders?** Nearly always this.
2. Was the site redeployed after the key was added? Pages binds variables at deploy
   time — a secret added after the last deploy is not visible to the running site.
3. Check Brevo's own **Transactional → Logs** — it shows accepted-then-blocked sends,
   which is exactly the failure that is invisible from the website's side.
4. Check the function's logs: `npx wrangler pages deployment tail --project-name=<project>`

## Spam

The hidden `website` field catches most automated spam at zero cost to real visitors.
Do not add anything stronger by default.

If spam does become a problem, Cloudflare Turnstile is the next step — a visitor-facing
check that is usually invisible. Two traps if you add it, both of which have already
been hit:

- **Do not give the widget's container `id="turnstile"`.** Every HTML `id` becomes a
  global variable, so `<div id="turnstile">` becomes `window.turnstile`, and Turnstile's
  own script reads that as "already loaded" and never renders the widget. Use
  `id="turnstile-widget"`.
- **Reset the widget after every submission.** A token is single-use and expires in
  minutes. Without a reset, a second submission — after a validation error, or a second
  enquiry in one visit — replays a spent token and is rejected.

Register the widget for every hostname it will appear on: the live domain, the `www`
form, `<project>.pages.dev`, and `localhost`. A host outside that list renders an error
instead of a challenge. And never recreate a widget to get a fresh secret — that
invalidates the site key already published in the page.
