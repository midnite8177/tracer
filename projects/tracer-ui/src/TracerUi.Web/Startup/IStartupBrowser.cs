namespace TracerUi.Web.Startup;

/// <summary>What the app does with its own address once it is listening.</summary>
public interface IStartupBrowser
{
    void Open(string url);
}
