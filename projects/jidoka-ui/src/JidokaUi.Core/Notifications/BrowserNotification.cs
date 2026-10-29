namespace JidokaUi.Core.Notifications;

/// <summary>
/// One notification for the browser to show. The tag names what it announces, so a browser that
/// holds the same notification from a second open tab shows it once.
/// </summary>
/// <param name="Tag">Names the event or the stale spell, and nothing else shares it.</param>
/// <param name="Address">The page that a press on the notification opens.</param>
public sealed record BrowserNotification(string Tag, string Title, string Body, string Address);
