using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using JidokaUi.Core.Beads;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;
using JidokaUi.Tests.Projects;
using JidokaUi.Web.Startup;

namespace JidokaUi.Tests.Startup;

/// <summary>
/// The whole app behind an HTTP client, so that a test reads the response that a browser gets before
/// any circuit is live.
/// </summary>
public sealed class AnAppOverHttp : WebApplicationFactory<JidokaUi.Web.Components.App>
{
    /// <summary>The bd that this app runs, which holds every command line that reached it.</summary>
    public FakeBd Bd { get; } = FakeBd.ThatAnswersReady();

    /// <summary>The projects that the registry of this app holds, which a test names in an address.</summary>
    public IReadOnlyList<ProjectPath> Projects { get; } =
        [ProjectPath.From("/jidoka-ui-tests/first"), ProjectPath.From("/jidoka-ui-tests/second")];

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureServices(services =>
        {
            var store = new InMemoryProjectRegistryStore();
            store.Hold(new ProjectRegistry(Projects, []));

            // Without the stand-in below, every test run opens a browser tab on the machine.
            services.RemoveAll<IStartupBrowser>();
            services.RemoveAll<IBdProcess>();
            services.RemoveAll<IProjectRegistryStore>();
            services.AddSingleton<IStartupBrowser>(new NoBrowser());
            services.AddSingleton<IBdProcess>(Bd);
            services.AddSingleton<IProjectRegistryStore>(store);
        });
    }

    private sealed class NoBrowser : IStartupBrowser
    {
        public void Open(string url)
        {
        }
    }
}
