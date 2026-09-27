using Bunit;
using TracerUi.Core.Projects;
using TracerUi.Web.Components.Layout;

namespace TracerUi.Tests.Boards;

public static class APick
{
    /// <summary>Renders a project picker beside the page of this context and picks the project in it.</summary>
    public static void Of(BunitContext context, ProjectPath project)
    {
        context.Render<ProjectPicker>().Find("select.project-picker").Change(project.Value);
    }
}
