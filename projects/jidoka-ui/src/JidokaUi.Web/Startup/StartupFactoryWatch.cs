using JidokaUi.Core.Notifications;

namespace JidokaUi.Web.Startup;

/// <summary>Starts the factory watch of the app.</summary>
public sealed class StartupFactoryWatch : IStartupFactoryWatch
{
    private readonly FactoryWatch watch;

    public StartupFactoryWatch(FactoryWatch watch)
    {
        this.watch = watch;
    }

    public void Start() => watch.Start();
}
