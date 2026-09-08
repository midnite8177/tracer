using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TracerUi.Core.Beads;
using TracerUi.Core.Projects;
using TracerUi.Tests.Beads;
using TracerUi.Tests.Projects;
using TracerUi.Web.Startup;

namespace TracerUi.Tests.Startup;

/// <summary>
/// The whole app behind an HTTP client, so that a test reads the response that a browser gets before
/// any circuit is live.
/// </summary>
public sealed class AnAppOverHttp : WebApplicationFactory<TracerUi.Web.Components.App>
{
    /// <summary>The bd that this app runs, which holds every command line that reached it.</summary>
    public FakeBd Bd { get; } = FakeBd.ThatAnswersReady();

    /// <summary>The projects that the registry of this app holds, which a test names in an address.</summary>
    public IReadOnlyList<ProjectPath> Projects { get; } =
        [ProjectPath.From("/tracer-ui-tests/first"), ProjectPath.From("/tracer-ui-tests/second")];

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureServices(services =>
        {
            var store = new InMemoryProjectRegistryStore();
            store.Save(new ProjectRegistry(Projects, []));

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
