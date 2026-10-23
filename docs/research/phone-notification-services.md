# Notification services that reach a phone

Research for the wayfinder map "Design new tracer factory workflow". When a
task needs Jeff, the factory comments on the bead, adds the `human` label and
notifies him. This note compares the services that could carry that
notification to his phone, from the home machine and from the Windows work
machine. For each one it covers the cost, whether it works over Tailscale,
whether a reply can come back tied to one bead, and what a corporate network
is likely to block.

I read the sources on 2026-10-20. Every claim links to the page it came
from, and a list near the end names the claims I could not confirm.

## Short answer

Web push from tracer-ui fits best at home. tracer-ui already has a detail
page per bead with "Add a comment", and the address of that page carries the
bead's project. A notification that opens the address puts Jeff on the one
bead the factory asked about, and his comment goes through `bd` like any
other write. iOS delivers web push to a home-screen web app from iOS 16.4
on. HTTPS is the hard requirement. tracer-ui serves plain HTTP today, and a
service worker runs only on an origin with a valid certificate. Tailscale's
HTTPS feature and `tailscale serve` give the machine a Let's Encrypt
certificate for its `ts.net` name, which should satisfy iOS. I found no
source that tests that exact setup, so a device test comes first.

On iOS, no service here lets Jeff type a reply inside the notification. ntfy
and Pushover carry a link, and ntfy adds up to three buttons that each fire
one fixed HTTP request. With either, the reply still happens on the tracer-ui
page the link opens, and that needs the phone on Tailscale.

Only the chat services have threads, where one typed reply maps to one
bead. Those are Telegram, Discord, Mattermost and Rocket.Chat. Telegram
needs the least wiring. A bot long-polls over outbound HTTPS, and each reply
carries the message it answers. The price is that bead text sits on a third
party's servers. A corporate filter is also more likely to block a chat
service than anything else on this list.

The work machine is where the design gets tight. A reply through tracer-ui
needs the phone to reach a tracer-ui that holds the bead. If corporate
policy, or a firewall that inspects TLS, keeps Tailscale off the work
machine, the only reply path left is a cloud chat bot, and only if the
network lets that traffic out.

## Comparison

| Service | Cost | Over Tailscale | Reply tied to one bead | Corporate network friction |
|---|---|---|---|---|
| Web push from tracer-ui | Free, no Apple developer account | Yes, behind `tailscale serve` HTTPS. Apple or Google deliver the alert, so it arrives with Tailscale off. Opening it needs Tailscale | Yes, by link. The tap opens the bead's page and Jeff comments there. No buttons or text field on iOS | Sender must reach `*.push.apple.com` or `fcm.googleapis.com`. A phone on corporate Wi-Fi needs the APNs ports |
| ntfy, self-hosted | Free and open source | Yes. For iOS the home server must also reach ntfy.sh, and the phone needs Tailscale to fetch the message | By link, plus up to three buttons that send a fixed HTTP request. No text input, no threads | The work machine needs Tailscale to reach the home server |
| ntfy.sh | Free up to 250 messages a day. Paid tiers are $6, $12 or $25 a month | Not needed | Same as self-hosted | How web filters classify ntfy.sh is unconfirmed |
| Pushover | $4.99 once per platform after a 30-day trial. 10,000 messages a month free | Not needed | By link only. Emergency priority returns a one-bit acknowledgment | `api.pushover.net` over HTTPS |
| Mattermost | Team Edition is free. Free push goes through a test service meant for non-commercial use, unencrypted, with no SLA | Yes, with the server on the tailnet. Push goes out through Mattermost's proxy | Yes, a root post per bead, and replies carry its `root_id` | The work machine needs Tailscale to reach the home server |
| Rocket.Chat | Starter is free up to 50 users with unlimited push. Push needs Rocket.Chat Cloud registration | Yes, with the server on the tailnet. Push goes out through `gateway.rocket.chat` | Yes, threads by `tmid` | Same as Mattermost |
| Discord | Free | Not needed | Yes, a thread per bead, a reply's `message_reference`, or a button that opens a text modal | Likely filed under chat by web filters, unconfirmed. The bot holds an outbound WebSocket to `gateway.discord.gg` |
| Telegram | Free | Not needed | Yes, `reply_to_message`, ForceReply, or a topic per bead in the private chat | Likely filed under instant messaging by web filters, unconfirmed. `api.telegram.org` over HTTPS |

The sections below carry the sources for each cell.

## The reply path tracer-ui already has

The detail page of tracer-ui writes, and one of its writes is "Add a
comment".[^tui-readme] The address of the detail page carries the bead's
project, so a link opened in a fresh tab lands on the right bead in the
right project.[^tui-adr11][^tui-adr16] A notification needs nothing more
than that address to route Jeff's reply to one bead. The needs-you view
already lists every bead that waits on a person across all
projects.[^tui-glossary]

tracer-ui binds the loopback address by default. The `--listen` flag binds
every interface with no password and no transport security, which is why
ADR 0003 keeps it for a trusted network.[^tui-adr3] `tailscale serve` would
let the app keep binding loopback while Tailscale terminates HTTPS and
proxies tailnet traffic to it. That still widens who reaches the board, to
every device on the tailnet, which is the trade-off ADR 0003 accepts for LAN
mode. The change does not contradict the ADR, but it deserves its own ADR
when it is built.

## Web push from tracer-ui

### What iOS requires

- iOS and iPadOS 16.4 added web push for web apps added to the Home
  Screen.[^webkit-ios] A Safari tab does not get it.
- The web app needs a manifest whose `display` is `standalone` or
  `fullscreen`.[^webkit-ios]
- The permission request must come from a user gesture, such as a tap on
  a button.[^webkit-ios][^apple-webpush]
- No Apple Developer Program membership is needed.[^apple-webpush]
- Safari does not allow invisible pushes. If the service worker does not
  show a notification for a push, Safari revokes the
  permission.[^apple-webpush]
- The payload limit is 4 KB. The `TTL` header lets Apple hold an
  undelivered message for up to 30 days, and `Urgency: high` asks for
  immediate delivery.[^apple-webpush]
- The server signs each request with a VAPID key pair. The public key must
  match the one passed to `PushManager.subscribe`.[^apple-webpush]
- If the network limits what the sending server can reach, it must allow
  `https://*.push.apple.com`.[^apple-webpush]

### HTTPS and the certificate

Service workers run only in a secure context, which means HTTPS, with an
exception for `http://localhost`.[^mdn-sw] An `http://` origin on a private
address is not a secure context.[^mdn-secure] So the address the README gives a
phone in LAN mode, `http://<the address of this machine>:5099`, cannot
install a push-capable web app.[^tui-readme] The ntfy docs put the same rule plainly. Service workers will not
run on origins with untrusted certificates, so the certificate has to be
valid.[^ntfy-webpush]

Tailscale's HTTPS feature asks Let's Encrypt for a certificate for the
machine's tailnet name. It needs MagicDNS, and it proves control of the
name through a `*.ts.net` TXT record, so the machine never has to be
reachable from the internet. The certificates expire after 90 days. When
you run `tailscale cert` yourself, renewal is your job.[^ts-https]
`tailscale serve` proxies tailnet traffic to a local port over HTTPS with a
certificate it provisions itself. It serves the tailnet only, and with
`--bg` it resumes after a reboot.[^ts-serve][^ts-serve-cli] An address of
the form `https://my-node.example.ts.net/` is what the phone would
install.[^ts-serve-cli]

Every certificate lands in the public Certificate Transparency log, machine
name included. Tailscale warns against the feature when a machine name holds
anything sensitive.[^ts-https]

Tailscale's Personal plan is free for up to six users with unlimited
devices.[^ts-pricing] The pricing page did not say whether HTTPS and Serve
are on that plan. I expect they are, but did not confirm it.

### How the push travels

tracer-ui would act as the application server. It encrypts the payload for
the phone and posts it to the endpoint in the subscription.[^apple-webpush]
RFC 8291 encrypts the message so the push service cannot read or alter
it.[^rfc8291] On iOS the endpoint is Apple's push service. On Android with
Chrome it is a Google host such as `fcm.googleapis.com`.[^ntfy-webpush]

The phone receives the push from Apple over the internet, so Tailscale plays
no part in delivery. Tailscale has to be up when Jeff installs the web app,
grants permission and subscribes, and again when he taps the notification
and the page loads. No Apple or WebKit page I read says the origin must be
reachable from the internet, and none of the steps they list has Apple
contact the origin. That is my reading of the protocol, not a documented
promise.

### Taps, buttons and routing to one bead

MDN's compatibility data lists the `actions`, `tag` and `requireInteraction`
notification options as unsupported in Safari, iOS
included.[^mdn-bcd-swr][^mdn-bcd-notif] So an iOS notification has no
buttons, and a second push for the same bead does not replace the first. The
standard gives no text field in any browser either. A `NotificationAction`
holds only `action`, `title`, `navigate` and `icon`.[^whatwg-notif] Chrome
on Android shows buttons, but still no text field.[^mdn-bcd-swr]

The tap itself is the routing. WebKit says that when the user activates a
notification, the service worker gets an event for it.[^webkit-meet] MDN's
compatibility data marks `notificationclick` as unsupported on Safari for
iOS.[^mdn-bcd-swg] The two disagree and I could not settle it from
documents. Declarative Web Push sidesteps the question on iOS 18.4 and
later. The payload carries a required `navigate` URL that the browser opens
on activation, and no service worker has to run.[^webkit-declarative] Set
`navigate` to the bead's tracer-ui address and the tap opens that bead.

### From the work machine

A push subscription belongs to one service worker, and so to one
origin.[^mdn-push] The VAPID public key on each request must match the key
the subscription was made with.[^apple-webpush] The work machine could push
to the subscription that the home tracer-ui holds only if it also had the
key pair and the subscription, and the tap would still open the home origin.
If the bead lives only on the work machine, the home tracer-ui has nothing
to show. A second tracer-ui on the work machine would mean a second
home-screen app, and the phone would have to reach the work machine over
Tailscale.

## ntfy

### Cost

ntfy is open source under Apache 2.0 and GPLv2.[^ntfy-faq] The server runs
on Linux, in Docker and on Windows. On macOS only the CLI is supported, so a
Mac at home would run the server in Docker.[^ntfy-install]

The public server ntfy.sh is free up to 250 messages a day per IP address,
and it keeps messages for 12 hours. Supporter costs $6 a month or $60 a year
for 2,500 messages a day. Pro costs $12 a month or $120 a year for 20,000.
Business costs $25 a month or $240 a year for 50,000.[^ntfy-tiers][^ntfy-limits]
Without access control, the topic name is the password, so a random topic
name is the only protection on the free tier.[^ntfy-faq]

### Over Tailscale

A self-hosted server on the tailnet works with Android. The app keeps a
connection open through a foreground service.[^ntfy-phone] That means the
phone keeps Tailscale connected all day.

iOS takes a detour. The self-hosted server sends ntfy.sh a poll request
that holds only the message ID, ntfy.sh pushes through Firebase and APNs,
and the phone then fetches the real message from the self-hosted
server.[^ntfy-config] If the phone cannot reach that server, iOS shows only
"New message".[^ntfy-known] So the home server needs outbound access to
ntfy.sh, and the phone needs Tailscale up for the text to appear. The author
calls the iOS app "very bare bones and quite frankly a little buggy" and says
its development is paused.[^ntfy-faq]

### Reply

A message can carry a click URL and up to three action buttons. `view`
opens a URL. `http` sends a POST, GET or PUT with headers and a body of your
choosing. Both work on Android, iOS and in Firefox. `broadcast` is
Android-only, and `copy` does not reach iOS.[^ntfy-publish] No action takes
typed text, and ntfy has no threads. A message holds at most 4,096
bytes.[^ntfy-limits] Updating or deleting a delivered notification by
sequence ID works on Android and the web app only.[^ntfy-publish]

The phone itself sends the `http` request, so a tailnet URL works only while
Tailscale is up. Buttons fit canned answers, such as approve or reject, with
the bead id in the URL. Anything longer goes through the tracer-ui link.

### From the work machine

The work machine can publish to ntfy.sh over HTTPS. To publish to the home
server, it needs Tailscale.

## Pushover

### Cost

Pushover costs $4.99 once per platform after a 30-day trial. One purchase
covers every device on that platform.[^pushover-pricing] Each account sends
10,000 messages a month free, shared across its
applications.[^pushover-limits] Pushover for Teams costs $5 per user per
month.[^pushover-pricing]

### Sending

The API takes HTTPS posts to `https://api.pushover.net/1/messages.json`. A
message holds 1,024 characters and a title 250. A supplementary `url` of up
to 512 characters, with a `url_title`, rides along.[^pushover-api] That URL
can be the bead's tracer-ui address on the tailnet. Tailscale plays no other
part.

### Reply

Pushover has no reply. "Actionable notifications" is an open user idea on
its support site with no staff response.[^pushover-idea] The only signal
back is emergency priority. The message repeats until Jeff acknowledges it,
and the sender can poll a receipt for `acknowledged`, no faster than every
5 seconds and for up to a week. A callback is the other option, but it must
be reachable from the internet.[^pushover-api][^pushover-receipts] Polling
needs only outbound traffic, so a factory on the tailnet can learn that Jeff
acknowledged the notification. It cannot learn his answer.

## Mattermost

### Cost and editions

In v11, Team Edition ships under an MIT-compiled license and allows up to
250 users. Entry is free under a commercial license, with planned caps of
10,000 messages and 10,000 push notifications a month.[^mm-v11] That announcement
is a forum post, and the page does not confirm the poster works for
Mattermost. The paid plans publish no prices.[^mm-pricing] The server runs
on Linux, in containers or on Kubernetes.[^mm-deploy]

### Push

The server sends pushes through a Mattermost proxy. The hosted service with
an uptime SLA is for Enterprise, Professional and Cloud customers. The free
test service, TPNS, is for non-commercial self-hosted servers and is "not
recommended for use in production".[^mm-env] Its terms say messages sent
through it "will not be encrypted" and are provided as-is.[^mm-terms]
Apple and Google accept pushes only from a service that holds the app's own
key, so a self-hosted proxy goes with mobile apps you build and sign
yourself.[^mm-faq][^mm-mpns]

### Over Tailscale

Mattermost's FAQ suggests a per-device VPN for a server on a private
network.[^mm-faq] The alert reaches the phone through the proxy, Apple and
Google. Reading the thread needs the app to reach the server, so it needs
Tailscale.

### Reply

The factory would create one root post per bead. A post made with
`root_id` comments on that post, and `GET /api/v4/posts/{post_id}/thread`
returns the whole thread.[^mm-api] Outgoing webhooks are a poor fit. They
watch public channels only and fire on trigger words at the start of a
message.[^mm-outgoing] Interactive dialogs can collect free text in a
`textarea` and post it back to the integration.[^mm-dialogs] The Mattermost
server sends those requests, and an integration on a private address has to
be allowed through `AllowedUntrustedInternalConnections`.[^mm-interactive]

My read is that this is a lot of server to run for one person, and the free
push path is a test service.

## Rocket.Chat

### Cost

Starter is a free self-managed workspace for up to 50 users, with unlimited
push. Community allows up to 100 concurrent users and 10,000 push
notifications a month, and Rocket.Chat says it does not suit business-critical
production use. Pro became a legacy plan on April 29,
2026.[^rc-plans][^rc-pricing]

### Push and Tailscale

Push needs the server registered with Rocket.Chat Cloud and outbound access
to `https://gateway.rocket.chat`. When the monthly quota runs out,
Rocket.Chat stops sending pushes until it resets. Hiding message content
from Apple and Google needs a premium plan.[^rc-push] Registration means a
Rocket.Chat Cloud account, which I did not create. As with Mattermost, the
server can live on the tailnet, and the phone needs Tailscale to read the
thread.

### Reply

`chat.sendMessage` takes a `tmid` to post inside a thread, and
`chat.getThreadMessages` reads a thread by its `tmid`.[^rc-send][^rc-thread]
One thread per bead maps each reply to one bead.

## Discord

### Cost

Discord's getting-started guide says a server is free to create.[^discord-start]
The developer docs I read give no price for an app or a bot.

### Connection

A bot opens a WebSocket to the Gateway, at a URL such as
`wss://gateway.discord.gg`.[^discord-gateway] Interactions arrive either over
the Gateway or at an HTTP endpoint, never both.[^discord-interactions] The
Gateway route needs no inbound URL, so the factory can run behind any NAT,
and Tailscale plays no part.

### Reply

- A public thread starts from a message and shares that message's id, so
  the factory stores one id per bead for both.[^discord-threads]
- A reply is message type 19, and its `message_reference.message_id` names
  the message it answers.[^discord-message]
- A button can answer with a modal, interaction callback type 9, which
  collects text. The bot must answer an interaction within 3
  seconds.[^discord-interactions]

The privileged `MESSAGE_CONTENT` intent gates message text. Without it a
bot still sees text in DMs with it and in messages that mention it. Discord requires approval of the intent for verified apps, and
verification is required at 100 servers.[^discord-gateway] The threads docs
describe threads only inside servers,[^discord-threads] so a DM setup would
rely on replies instead.

## Telegram

### Cost

The Bot API is free. Telegram's FAQ says bots "are able to message their
users at no cost", with a limit of about one message per second per
chat.[^tg-faq]

### Connection

A bot gets updates through `getUpdates` long polling or through a webhook,
never both. Telegram keeps undelivered updates for no longer than 24
hours.[^tg-api] A webhook must be a URL that Telegram can reach, on port 443,
80, 88 or 8443.[^tg-api] Long polling needs only outbound HTTPS to
`api.telegram.org`, so it works from either machine without Tailscale. The
24-hour limit matters, though. A factory that stays down longer than a day
loses every reply older than that.

### Reply

- `reply_to_message` holds the original message, so the factory maps the
  message id it sent back to the bead.[^tg-api]
- `ForceReply` opens the reply box as if Jeff had tapped Reply on the bot's
  message.[^tg-api]
- `createForumTopic` creates a topic in a private chat with a user, and
  messages carry `message_thread_id` when the bot has forum topic mode
  turned on. That gives one topic per bead.[^tg-api]
- Inline buttons carry `callback_data` of 1 to 64 bytes, enough for a bead
  id and a canned answer.[^tg-api]

Bead text goes through Telegram's servers.

## What a corporate network is likely to block

### The phone on corporate Wi-Fi

On iOS each of these paths ends in Apple's push service. ntfy hands off to
Firebase and APNs,[^ntfy-config] Mattermost hands off to APNs and
FCM,[^mm-faq] and web push goes to Apple's push service by
design.[^apple-webpush] I assume Discord and Telegram use APNs too, since a
native iOS app has no other background push, but neither documents it.
Apple devices hold a connection to APNs on TCP 5223 and fall back to 443.
The fallback crosses a proxy only if the proxy does not decrypt it. Apple
suggests allowing the whole `17.0.0.0/8` block.[^apple-apns] Pushover's
support page adds that Android needs outbound TCP 5228.[^pushover-wifi] On
cellular none of this applies. A Wi-Fi network that blocks these ports
silences every service in the table at once, so it does not separate them.

### The work machine sending out

| Service | What the factory must reach |
|---|---|
| Web push | `*.push.apple.com` for iOS, a Google push host for Chrome on Android |
| ntfy.sh | `ntfy.sh` over HTTPS |
| ntfy, Mattermost or Rocket.Chat at home | The home machine over Tailscale |
| Pushover | `api.pushover.net` over HTTPS |
| Discord | `discord.com` and a WebSocket to `gateway.discord.gg` |
| Telegram | `api.telegram.org` over HTTPS |

Web filters block by category. Microsoft Defender for Endpoint, one filter
a managed Windows machine may run, has "Chat" and "Instant messaging"
categories under Leisure, and it files remote proxy sites under "Illegal
software".[^mde-wcf] Its web content filtering works in browsers only, so it
would not see a factory process. A perimeter proxy or firewall sees every
process. I found no vendor source for how the common filters classify each
domain here. My guess is that Discord and Telegram are the likeliest blocks,
that Apple's push hosts and Pushover are the least likely, and that ntfy.sh
could go either way. All of that is unconfirmed until it is tried on the
work network.

### Tailscale on the work machine

Tailscale wants outbound UDP 41641 and 3478 and TCP 443. When UDP is
blocked, it relays through its DERP servers over HTTPS on
443.[^ts-ports] A FortiGate that inspects TLS breaks the connection to
Tailscale's control plane, and the only fix Tailscale gives is to turn that
inspection off or narrow it. Tailscale also says to check for rules that
block its traffic as a proxy.[^ts-firewalls] Corporate policy may forbid a
VPN client on a managed machine anyway. That depends on Jeff's employer and
is unconfirmed.

## Not confirmed

- That iOS installs and pushes to a home-screen web app whose origin is a
  `ts.net` name served by `tailscale serve`. Every requirement I found is
  met on paper, but no source tests this setup.
- Whether Apple's push service ever needs to reach the origin. Nothing I
  read says so.
- Whether `tailscale serve` renews its certificate on its own, and whether it
  passes WebSockets, which the tracer-ui circuit needs. The docs I read are
  silent on both.
- Whether HTTPS and Serve are included in Tailscale's free Personal plan.
- Whether iOS fires `notificationclick` for web push. WebKit and MDN
  disagree. Declarative Web Push's `navigate` avoids the question on iOS
  18.4 and later.
- Which push service Mattermost Entry uses, and whether its planned caps are
  in force.
- Whether Discord threads exist in DMs.
- That the Discord and Telegram iOS apps receive through APNs.
- How the work network classifies each domain, and whether it allows
  Tailscale.

## Sources

[^tui-readme]: tracer-ui README, "Triage on one bead". [projects/tracer-ui/README.md](../../projects/tracer-ui/README.md)
[^tui-adr11]: [ADR 0011, the address of a bead carries its project](../../projects/tracer-ui/docs/adr/0011-the-address-of-a-bead-carries-its-project.md)
[^tui-adr16]: [ADR 0016, the address carries the active project](../../projects/tracer-ui/docs/adr/0016-the-address-carries-the-active-project.md)
[^tui-glossary]: tracer-ui glossary, "Needs-you view". [projects/tracer-ui/GLOSSARY.md](../../projects/tracer-ui/GLOSSARY.md)
[^tui-adr3]: [ADR 0003, the app binds localhost](../../projects/tracer-ui/docs/adr/0003-localhost-by-default.md)
[^webkit-ios]: WebKit, "Web Push for Web Apps on iOS and iPadOS". https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
[^apple-webpush]: Apple, "Sending web push notifications in web apps and browsers". https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers
[^mdn-sw]: MDN, "Service Worker API". https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API
[^mdn-secure]: MDN, "Secure contexts". https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts
[^mdn-push]: MDN, "Push API". https://developer.mozilla.org/en-US/docs/Web/API/Push_API
[^ntfy-webpush]: ntfy docs, "Web Push". https://docs.ntfy.sh/config/#web-push
[^ts-https]: Tailscale, "Enabling HTTPS". https://tailscale.com/kb/1153/enabling-https
[^ts-serve]: Tailscale, "Tailscale Serve". https://tailscale.com/kb/1312/serve
[^ts-serve-cli]: Tailscale, "tailscale serve command". https://tailscale.com/kb/1242/tailscale-serve
[^ts-pricing]: Tailscale pricing. https://tailscale.com/pricing
[^rfc8291]: RFC 8291, "Message Encryption for Web Push". https://datatracker.ietf.org/doc/html/rfc8291
[^mdn-bcd-swr]: MDN browser-compat-data, `ServiceWorkerRegistration.showNotification` options. https://github.com/mdn/browser-compat-data/blob/main/api/ServiceWorkerRegistration.json
[^mdn-bcd-notif]: MDN browser-compat-data, `Notification`. https://github.com/mdn/browser-compat-data/blob/main/api/Notification.json
[^mdn-bcd-swg]: MDN browser-compat-data, `ServiceWorkerGlobalScope` events. https://github.com/mdn/browser-compat-data/blob/main/api/ServiceWorkerGlobalScope.json
[^whatwg-notif]: WHATWG Notifications API Standard, `NotificationAction`. https://notifications.spec.whatwg.org/
[^webkit-meet]: WebKit, "Meet Web Push". https://webkit.org/blog/12945/meet-web-push/
[^webkit-declarative]: WebKit, "Meet Declarative Web Push". https://webkit.org/blog/16535/meet-declarative-web-push/
[^ntfy-faq]: ntfy FAQ. https://docs.ntfy.sh/faq/
[^ntfy-install]: ntfy install docs, macOS and Windows. https://docs.ntfy.sh/install/
[^ntfy-tiers]: ntfy.sh tier list, from the server's own API. https://ntfy.sh/v1/tiers
[^ntfy-limits]: ntfy docs, "Limitations". https://docs.ntfy.sh/publish/#limitations
[^ntfy-phone]: ntfy docs, "Subscribe from your phone". https://docs.ntfy.sh/subscribe/phone/
[^ntfy-config]: ntfy docs, "iOS instant notifications". https://docs.ntfy.sh/config/#ios-instant-notifications
[^ntfy-known]: ntfy docs, "Known issues". https://docs.ntfy.sh/known-issues/
[^ntfy-publish]: ntfy docs, "Action buttons" and "Updating + deleting notifications". https://docs.ntfy.sh/publish/#action-buttons
[^pushover-pricing]: Pushover pricing. https://pushover.net/pricing
[^pushover-limits]: Pushover, "Message size and frequency limitations". https://support.pushover.net/i12-message-size-and-frequency-limitations
[^pushover-api]: Pushover API. https://pushover.net/api
[^pushover-idea]: Pushover ideas, "Actionable notifications". https://support.pushover.net/i231-actionable-notifications
[^pushover-receipts]: Pushover receipts and callbacks API. https://pushover.net/api/receipts
[^pushover-wifi]: Pushover, "Receiving Pushover messages but no push notifications". https://support.pushover.net/i15-receiving-pushover-messages-but-no-push-notifications
[^mm-v11]: Mattermost forum, "Mattermost v11 Changes in Free Offerings". https://forum.mattermost.com/t/mattermost-v11-changes-in-free-offerings/25126
[^mm-pricing]: Mattermost pricing. https://mattermost.com/pricing/
[^mm-deploy]: Mattermost, "Server deployment planning". https://docs.mattermost.com/deployment-guide/server/server-deployment-planning.html
[^mm-env]: Mattermost, "Environment configuration settings", push notification server. https://docs.mattermost.com/administration-guide/configure/environment-configuration-settings
[^mm-terms]: Mattermost, "Hosted Push Notifications Service Subscription Terms". https://mattermost.com/hpns-terms/
[^mm-mpns]: Mattermost, "Host your own push proxy service". https://docs.mattermost.com/deployment-guide/mobile/host-your-own-push-proxy-service.html
[^mm-faq]: Mattermost, "Mobile apps FAQ". https://docs.mattermost.com/deployment-guide/mobile/mobile-faq
[^mm-api]: Mattermost API spec, posts. https://github.com/mattermost/mattermost/blob/master/api/v4/source/posts.yaml
[^mm-outgoing]: Mattermost, "Outgoing webhooks". https://docs.mattermost.com/developers/integrate/webhooks/outgoing
[^mm-dialogs]: Mattermost, "Interactive dialogs". https://docs.mattermost.com/developers/integrate/plugins/interactive-dialogs
[^mm-interactive]: Mattermost, "Interactive messages". https://docs.mattermost.com/developers/integrate/plugins/interactive-messages
[^rc-plans]: Rocket.Chat docs, "Our plans". https://docs.rocket.chat/v1/docs/our-plans
[^rc-pricing]: Rocket.Chat pricing. https://www.rocket.chat/pricing
[^rc-push]: Rocket.Chat, "Push Notifications FAQ". https://docs.rocket.chat/docs/push-notifications-faq
[^rc-send]: Rocket.Chat API, "Send Message". https://developer.rocket.chat/apidocs/send-message
[^rc-thread]: Rocket.Chat API, "Get Thread Messages". https://developer.rocket.chat/apidocs/get-thread-messages
[^discord-start]: Discord, "Building your first Discord Bot". https://docs.discord.com/developers/quick-start/getting-started
[^discord-gateway]: Discord, "Gateway", including the Message Content intent. https://docs.discord.com/developers/events/gateway
[^discord-interactions]: Discord, "Receiving and Responding" to interactions. https://docs.discord.com/developers/interactions/receiving-and-responding
[^discord-threads]: Discord, "Threads". https://docs.discord.com/developers/topics/threads
[^discord-message]: Discord, "Message" resource. https://docs.discord.com/developers/resources/message
[^tg-faq]: Telegram, "Bots FAQ". https://core.telegram.org/bots/faq
[^tg-api]: Telegram, "Bot API". https://core.telegram.org/bots/api
[^apple-apns]: Apple Support, "If your Apple devices aren't getting Apple push notifications". https://support.apple.com/en-us/102266
[^mde-wcf]: Microsoft, "Web content filtering in Microsoft Defender for Endpoint". https://learn.microsoft.com/en-us/defender-endpoint/web-content-filtering
[^ts-ports]: Tailscale, "What firewall ports should I open to use Tailscale?". https://tailscale.com/kb/1082/firewall-ports
[^ts-firewalls]: Tailscale, "Using Tailscale with your firewall". https://tailscale.com/docs/integrations/firewalls
