using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Look;
using TracerUi.Core.Projects;
using TracerUi.Web.Components;
using TracerUi.Web.Components.Pages;
using TracerUi.Web.Startup;

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
    new FileProjectRegistryStore(
        RegistryFilePath.In(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData))));
builder.Services.AddSingleton<IBdProcess>(new BdProcess("bd"));
builder.Services.AddSingleton<BdAdapter>();
builder.Services.AddSingleton<BacklogReader>();
builder.Services.AddSingleton<BacklogCache>();
builder.Services.AddSingleton<NeedsYouReader>();
builder.Services.AddSingleton<ProjectWatchers>();
builder.Services.AddSingleton<BeadDetailReader>();
builder.Services.AddSingleton<BulkWriter>();
builder.Services.AddSingleton<ProjectCatalog>();
builder.Services.AddSingleton<SavedFilterCatalog>();
builder.Services.AddScoped<ActiveProjectSelection>();
builder.Services.AddScoped<CopyFeedback>();
builder.Services.AddScoped<BeadOpener>();
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
