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
}
