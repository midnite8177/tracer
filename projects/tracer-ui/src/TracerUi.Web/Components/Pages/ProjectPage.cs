using Microsoft.AspNetCore.Components;
using TracerUi.Core.Boards;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// A page that shows one project. Its address names the project in the query, and every change of
/// the address that could concern the page reaches <see cref="ShowTheAddressAsync"/>.
/// </summary>
public abstract class ProjectPage : ComponentBase
{
    /// <summary>
    /// The words that say bd did not answer a read which the page began after it had shown what an
    /// earlier read gave.
    /// </summary>
    protected const string NoAnswerAgain = "bd has not answered again.";

    private FollowedBacklog? followed;

    /// <summary>
    /// The project that the query of the address names, as Blazor reads it. Nothing reads this value,
    /// because the page reads the project from the whole address through its <see cref="PageProject"/>.
    /// The parameter exists because Blazor sets the parameters of a page again when its query
    /// changes only if the page takes a parameter from the query.
    /// </summary>
    [SupplyParameterFromQuery(Name = ProjectInTheAddress.QueryName)]
    public string? Project { get; set; }

    protected sealed override Task OnParametersSetAsync() => ShowTheAddressAsync();

    /// <summary>
    /// Shows what the current address asks for. Blazor calls it for every new route value and every
    /// change of the query, including the change that leaves the page before the router drops it.
    /// </summary>
    protected abstract Task ShowTheAddressAsync();

    /// <summary>
    /// Hands <paramref name="take"/> every change of the held backlog of the project that the page
    /// shows, on the renderer. A throw from it reaches the renderer as a throw of the page. The page
    /// calls <see cref="StopFollowingTheBacklog"/> when it goes.
    /// </summary>
    /// <param name="backlogs">The cache whose changes the page follows.</param>
    /// <param name="project">The project of the page, which decides whether a change concerns it.</param>
    /// <param name="take">What the page does with a change of its project.</param>
    protected void FollowTheBacklog(BacklogCache backlogs, PageProject project, Func<BacklogChange, Task> take)
    {
        followed = new FollowedBacklog(backlogs, project, take);
        backlogs.Changed += OnBacklogChanged;
    }

    /// <summary>Stops the changes that <see cref="FollowTheBacklog"/> hands the page.</summary>
    protected void StopFollowingTheBacklog()
    {
        if (followed is not null)
        {
            followed.Backlogs.Changed -= OnBacklogChanged;
        }
    }

    // A project watcher raises its change on a timer thread, so even the check of the project waits
    // for the renderer.
    private void OnBacklogChanged(BacklogChange change) =>
        _ = InvokeAsync(() => TakeOrHandTheThrowToTheRenderer(change));

    // Nothing awaits this read, so a throw would otherwise vanish with the task.
    private async Task TakeOrHandTheThrowToTheRenderer(BacklogChange change)
    {
        if (followed is not { } following || !following.Project.Shows(change.Project))
        {
            return;
        }

        try
        {
            await following.Take(change);
        }
        catch (Exception unexpected)
        {
            await DispatchExceptionAsync(unexpected);
        }
    }

    private sealed record FollowedBacklog(BacklogCache Backlogs, PageProject Project, Func<BacklogChange, Task> Take);
}
