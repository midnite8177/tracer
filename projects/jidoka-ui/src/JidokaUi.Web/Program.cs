using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Look;
using JidokaUi.Core.Projects;
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
builder.Services.AddSingleton<IBdProcess>(new BdProcess("bd"));
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton<BdAdapter>();
builder.Services.AddSingleton<BacklogReader>();
builder.Services.AddSingleton<BacklogCache>();
builder.Services.AddSingleton<NeedsYouReader>();
builder.Services.AddSingleton<IWriteReports>(services => new JournalCheckedWriteReports(
    new FileSystemWriteReports(),
    services.GetRequiredService<TimeProvider>(),
    JournalCheckedWriteReports.Interval));
builder.Services.AddSingleton<ProjectWatchers>();
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

app.Run();

return 0;
