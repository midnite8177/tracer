using System.Globalization;

namespace JidokaUi.Web.Startup;

/// <summary>The address that the app binds, and whether that address reaches machines other than this one.</summary>
public sealed record BindAddress(int Port, bool ReachesEveryInterface)
{
    private const int DefaultPort = 5099;
    private const string ListenFlag = "--listen";
    private const string ListenWord = "listen";
    private const string PortFlag = "--port";
    private const string PortWord = "port";
    private const int HighestPort = 65535;
    private const string PortHint = $"Write {PortFlag} followed by a port number from 1 to 65535, such as {PortFlag} 5101.";

    /// <summary>The address that the server binds, which is every interface in LAN mode and the loopback otherwise.</summary>
    public string BoundAddress => ReachesEveryInterface ? $"http://0.0.0.0:{Port}" : $"http://localhost:{Port}";

    /// <summary>The address for the browser of this machine. The loopback name reaches the app in both modes.</summary>
    public string BrowseAddress => $"http://localhost:{Port}";

    public static BindAddress From(IReadOnlyList<string> arguments)
    {
        var reachesEveryInterface = false;
        int? namedPort = null;

        for (var index = 0; index < arguments.Count; index++)
        {
            var argument = arguments[index];
            if (IsTheListenFlag(argument))
            {
                reachesEveryInterface = true;
            }
            else if (LooksLikeTheListenFlag(argument))
            {
                throw new ArgumentException(
                    $"jidoka-ui does not know the argument {argument}. Write {ListenFlag} to bind every interface.");
            }
            else if (IsThePortFlag(argument))
            {
                if (namedPort is not null)
                {
                    throw new ArgumentException(
                        $"jidoka-ui does not know which port to bind, because {argument} appears more than once. {PortHint}");
                }

                index++;
                if (index == arguments.Count)
                {
                    throw new ArgumentException($"jidoka-ui found no port after {argument}. {PortHint}");
                }

                namedPort = PortFrom(arguments[index]);
            }
            else if (LooksLikeThePortFlag(argument))
            {
                throw new ArgumentException($"jidoka-ui does not know the argument {argument}. {PortHint}");
            }
        }

        return new BindAddress(namedPort ?? DefaultPort, reachesEveryInterface);
    }

    private static bool IsTheListenFlag(string argument) =>
        string.Equals(argument, ListenFlag, StringComparison.OrdinalIgnoreCase);

    private static bool LooksLikeTheListenFlag(string argument) =>
        argument.TrimStart('-', '/').StartsWith(ListenWord, StringComparison.OrdinalIgnoreCase);

    private static int PortFrom(string value)
    {
        if (!value.StartsWith('0')
            && int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out var port)
            && port <= HighestPort)
        {
            return port;
        }

        throw new ArgumentException($"jidoka-ui does not know the port {value}. {PortHint}");
    }

    private static bool IsThePortFlag(string argument) =>
        string.Equals(argument, PortFlag, StringComparison.OrdinalIgnoreCase);

    private static bool LooksLikeThePortFlag(string argument) =>
        argument.TrimStart('-', '/').StartsWith(PortWord, StringComparison.OrdinalIgnoreCase);
}
