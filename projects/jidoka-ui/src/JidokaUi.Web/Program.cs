using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Factory;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Look;
using JidokaUi.Core.Notifications;
using JidokaUi.Core.Projects;
using JidokaUi.Core.Spend;
using JidokaUi.Web.Components;
using JidokaUi.Web.Components.Pages;
using JidokaUi.Web.Startup;

var builder = WebApplication.CreateBuilder(args);

BindAddress bindAddress;
try
{
    bindAddress = BindAddress.From(args);
}
catch (ArgumentException exception)
{
    Console.Error.WriteLine(exception.Message);
    return 1;
}

builder.WebHost.UseUrls(bindAddress.BoundAddress);

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

builder.Services.AddSingleton<IProjectRegistryStore>(_ =>
{
    var userConfigurationDirectory = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
    var store = new FileProjectRegistryStore(
        RegistryFilePath.In(userConfigurationDirectory),
        FileProjectRegistryStore.LockTimeout);
    store.CopyFromWhenAbsent(RegistryFilePath.EarlierIn(userConfigurationDirectory));
    return store;
});
var jidokaHome = JidokaHome.Locate(
    Environment.GetEnvironmentVariable(JidokaHome.EnvironmentVariable),
    Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
builder.Services.AddSingleton(new JidokaPages(jidokaHome));
builder.Services.AddSingleton<IOnboardedProjects>(new OnboardedProjectFiles(jidokaHome));
builder.Services.AddSingleton<IBdProcess>(new BdProcess("bd"));
builder.Services.AddSingleton<IJidokaProcess, JidokaProcess>();
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton<BdAdapter>();
builder.Services.AddSingleton(services => new JidokaAdapter(
    services.GetRequiredService<IJidokaProcess>(),
    services.GetRequiredService<BdAdapter>(),
    jidokaHome,
    services.GetRequiredService<TimeProvider>()));
builder.Services.AddSingleton<BacklogReader>();
builder.Services.AddSingleton<BacklogCache>();
builder.Services.AddSingleton<NeedsYouReader>();
builder.Services.AddSingleton<FactoryReader>();
builder.Services.AddSingleton(new Ledger(jidokaHome));
builder.Services.AddSingleton<SpendReader>();
builder.Services.AddSingleton<IWriteReports>(services => new JournalCheckedWriteReports(
    new FileSystemWriteReports(),
    services.GetRequiredService<TimeProvider>(),
    JournalCheckedWriteReports.Interval));
builder.Services.AddSingleton<ProjectWatchers>();
builder.Services.AddSingleton(new Heartbeats(jidokaHome));
builder.Services.AddSingleton<FactoryWatch>();
builder.Services.AddSingleton<IStartupFactoryWatch, StartupFactoryWatch>();
builder.Services.AddSingleton<BeadDetailReader>();
builder.Services.AddSingleton<BulkWriter>();
builder.Services.AddSingleton<ProjectCatalog>();
builder.Services.AddSingleton<SavedFilterCatalog>();
builder.Services.AddScoped<ActiveProjectSelection>();
builder.Services.AddScoped<CopyFeedback>();
builder.Services.AddScoped<BeadOpener>();
builder.Services.AddScoped<SwitchAddress>();
builder.Services.AddSingleton(bindAddress);
builder.Services.AddSingleton<IStartupBrowser, BrowserTab>();

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
}

app.UseStatusCodePagesWithReExecute("/not-found", createScopeForStatusCodePages: true);
app.UseAntiforgery();

app.MapStaticAssets();
app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

var startupBrowser = app.Services.GetRequiredService<IStartupBrowser>();
app.Lifetime.ApplicationStarted.Register(() => startupBrowser.Open(bindAddress.BrowseAddress));

var startupFactoryWatch = app.Services.GetRequiredService<IStartupFactoryWatch>();
app.Lifetime.ApplicationStarted.Register(startupFactoryWatch.Start);

app.Run();

return 0;
