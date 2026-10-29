namespace JidokaUi.Web.Startup;

/// <summary>
/// What the app does for the factory once it is listening: it starts the watch that raises the
/// browser notifications. The watch reads every project of the registry, so a test of the app
/// stands in for it and no test run reads a project that it did not name.
/// </summary>
public interface IStartupFactoryWatch
{
    void Start();
}
