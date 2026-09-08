namespace TracerUi.Web.Startup;

/// <summary>The address that the app binds, and whether that address reaches machines other than this one.</summary>
public sealed record BindAddress(string BoundAddress, bool ReachesEveryInterface)
{
    private const int Port = 5099;
    private const string ListenFlag = "--listen";
    private const string ListenWord = "listen";

    private static readonly string LoopbackAddress = $"http://localhost:{Port}";
    private static readonly string EveryInterfaceAddress = $"http://0.0.0.0:{Port}";

    /// <summary>The address for the browser of this machine. The loopback name reaches the app in both modes.</summary>
    public string BrowseAddress => LoopbackAddress;

    public static BindAddress From(IReadOnlyList<string> arguments)
    {
        var reachesEveryInterface = false;

        foreach (var argument in arguments)
        {
            if (IsTheListenFlag(argument))
            {
                reachesEveryInterface = true;
            }
            else if (LooksLikeTheListenFlag(argument))
            {
                throw new ArgumentException(
                    $"tracer-ui does not know the argument {argument}. Write {ListenFlag} to bind every interface.");
            }
        }

        return reachesEveryInterface
            ? new BindAddress(EveryInterfaceAddress, ReachesEveryInterface: true)
            : new BindAddress(LoopbackAddress, ReachesEveryInterface: false);
    }

    private static bool IsTheListenFlag(string argument) =>
        string.Equals(argument, ListenFlag, StringComparison.OrdinalIgnoreCase);

    private static bool LooksLikeTheListenFlag(string argument) =>
        argument.TrimStart('-', '/').StartsWith(ListenWord, StringComparison.OrdinalIgnoreCase);
}
