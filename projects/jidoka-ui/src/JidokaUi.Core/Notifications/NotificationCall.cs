namespace JidokaUi.Core.Notifications;

/// <summary>The calls with which the app asks the browser to show a notification.</summary>
public static class NotificationCall
{
    /// <summary>The object on the window that holds the calls.</summary>
    public const string Holder = "jidokaNotifications";

    /// <summary>Answers default, granted, denied or unsupported, and asks nothing of the person.</summary>
    public const string Permission = "permission";

    /// <summary>Asks the person for permission and answers as <see cref="Permission"/> does. A browser allows it only inside a press.</summary>
    public const string Request = "request";

    /// <summary>Shows one notification when the person granted permission.</summary>
    public const string Show = "show";

    /// <summary>The permission with which a browser says that the person was not asked yet.</summary>
    public const string Default = "default";

    /// <summary>The name that a caller passes to the browser for one of the calls.</summary>
    public static string Name(string call) => $"{Holder}.{call}";
}
